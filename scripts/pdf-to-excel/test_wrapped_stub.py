"""Original closed-grid fixtures for wrapped body-label recovery."""

import copy
import io
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import pdfplumber
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_wrapped_stub import recover


def fixture():
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(400, 300))
    c.setFont("Helvetica", 10)
    specs = [
        (0, 0, "Category", 35, 250),
        (0, 1, "Prior", 205, 250),
        (0, 2, "Later", 285, 250),
        (1, 0, "Roasted beans,", 35, 230),
        (2, 0, "ground blend", 35, 216),
        (1, 1, "0.230", 205, 230),
        (1, 2, "001.200", 285, 230),
    ]
    for _, _, text, x, y in specs:
        c.drawString(x, y, text)
    for x in [30, 200, 280, 360]:
        c.line(x, 205, x, 265)
    for y in [265, 243, 205]:
        c.line(30, y, 360, y)
    c.save()
    with pdfplumber.open(io.BytesIO(buf.getvalue())) as d:
        p = d.pages[0]
        chars = copy.deepcopy(p.chars)
        edges = copy.deepcopy(p.edges)
        tables = [
            SimpleNamespace(bbox=t.bbox, cells=copy.deepcopy(t.cells))
            for t in p.find_tables()
        ]
    cells = []
    for r, col, text, x, y in specs:
        gs = [
            g
            for g in chars
            if abs(g["matrix"][5] - y) < 0.01 and x <= g["x0"] < x + 150
        ]
        # For numeric columns isolate the adjacent text run.
        if col == 1:
            gs = [g for g in gs if g["x1"] < 280]
        b = {
            "l": min(g["x0"] for g in gs),
            "t": min(g["top"] for g in gs),
            "r": max(g["x1"] for g in gs),
            "b": max(g["bottom"] for g in gs),
            "coord_origin": "TOPLEFT",
        }
        cells.append(
            {
                "text": text,
                "bbox": b,
                "start_row_offset_idx": r,
                "end_row_offset_idx": r + 1,
                "start_col_offset_idx": col,
                "end_col_offset_idx": col + 1,
                "row_span": 1,
                "col_span": 1,
                "column_header": r == 0,
                "row_section": False,
            }
        )
    page = SimpleNamespace(
        chars=chars,
        edges=edges,
        annots=[],
        images=[],
        bbox=(0, 0, 400, 300),
        cropbox=None,
        width=400,
        height=300,
        rotation=0,
        find_tables=lambda: tables,
    )
    item = {
        "data": {"num_rows": 3, "num_cols": 3, "table_cells": cells},
        "prov": [
            {"bbox": {"l": 30, "t": 35, "r": 360, "b": 95, "coord_origin": "TOPLEFT"}}
        ],
    }
    return item, page


class WrappedStubTests(unittest.TestCase):
    def test_closed_grid_preserves_values_and_input(self):
        item, page = fixture()
        before = copy.deepcopy(item)
        out = recover(item, page)
        self.assertEqual(out["data"]["num_rows"], 2)
        self.assertEqual(len(out["data"]["table_cells"]), 6)
        self.assertEqual(
            out["data"]["table_cells"][3]["text"], "Roasted beans,\nground blend"
        )
        self.assertEqual(
            out["data"]["table_cells"][-2:], item["data"]["table_cells"][-2:]
        )
        self.assertEqual(item, before)

    def test_malformed_metadata_and_real_third_row(self):
        for field, value in [
            ("row_span", 2),
            ("start_row_offset_idx", -1),
            ("end_col_offset_idx", 3),
            ("row_span", True),
            ("text", "ground 2"),
        ]:
            item, page = fixture()
            item["data"]["table_cells"][4][field] = value
            self.assertIs(recover(item, page), item)
        item, page = fixture()
        extra = copy.deepcopy(item["data"]["table_cells"][-1])
        extra.update(start_row_offset_idx=2, end_row_offset_idx=3)
        item["data"]["table_cells"].append(extra)
        self.assertIs(recover(item, page), item)
        item, page = fixture()
        item["data"]["table_cells"].append(
            copy.deepcopy(item["data"]["table_cells"][0])
        )
        self.assertIs(recover(item, page), item)

    def test_grid_geometry_and_partial_line(self):
        for edge in [
            {"x0": 35, "top": 80, "x1": 60, "bottom": 80},
            {"x0": 0, "top": float("nan"), "x1": 10, "bottom": 20},
            {},
        ]:
            item, page = fixture()
            page.edges.append(edge)
            self.assertIs(recover(item, page), item)
        item, page = fixture()
        page.find_tables = list
        self.assertIs(recover(item, page), item)
        item, page = fixture()
        tables = page.find_tables()
        tables[0].cells.pop()
        self.assertIs(recover(item, page), item)
        item, page = fixture()
        page.find_tables = lambda: (_ for _ in ()).throw(ValueError("bad finder"))
        self.assertIs(recover(item, page), item)
        item, page = fixture()
        page.cropbox = (31, 0, 400, 300)
        self.assertIs(recover(item, page), item)

    def test_annotation_image_and_unknown_bounds(self):
        for name in ["annots", "images"]:
            for obj in [
                {},
                {
                    "x0": 30,
                    "top": 40,
                    "x1": 60,
                    "bottom": 90,
                    "contents": "",
                    "data": {"AP": {}},
                },
                {"x0": float("nan"), "top": 40, "x1": 60, "bottom": 90},
            ]:
                item, page = fixture()
                setattr(page, name, [obj])
                self.assertIs(recover(item, page), item)
            item, page = fixture()
            setattr(page, name, [{"x0": 1, "top": 1, "x1": 10, "bottom": 10}])
            self.assertIsNot(recover(item, page), item)

    def test_font_superscript_indent_gap_and_source_loss(self):
        for field, value in [
            ("size", 6),
            ("fontname", "Other"),
            ("matrix", (1, 0.1, 0, 1, 35, 216)),
        ]:
            item, page = fixture()
            g = next(g for g in page.chars if g["matrix"][5] == 216)
            g[field] = value
            self.assertIs(recover(item, page), item)
        for offset in [3, 10]:
            item, page = fixture()
            for g in page.chars:
                if g["matrix"][5] == 216:
                    g["x0"] += offset
                    g["x1"] += offset
            self.assertIs(recover(item, page), item)
        item, page = fixture()
        g = copy.deepcopy(page.chars[0])
        g.update(x0=100, x1=105, top=80, bottom=90, text="X")
        page.chars.append(g)
        self.assertIs(recover(item, page), item)
        item, page = fixture()
        item["data"]["table_cells"][-1]["text"] = "001.201"
        self.assertIs(recover(item, page), item)

    def test_missing_boundary_and_invalid_empty_cell(self):
        item, page = fixture()
        page.edges = [e for e in page.edges if e["x0"] != e["x1"] or e["x0"] != 30]
        self.assertIs(recover(item, page), item)
        item, page = fixture()
        extra = copy.deepcopy(item["data"]["table_cells"][-1])
        extra.update(text="", start_row_offset_idx=2, end_row_offset_idx=3, bbox={})
        item["data"]["table_cells"].append(extra)
        self.assertIs(recover(item, page), item)

    def test_unknown_font_cannot_establish_shared_style(self):
        for font in (None, "", 123, "   "):
            item, page = fixture()
            for glyph in page.chars:
                if glyph["matrix"][5] in (230, 216) and glyph["x0"] < 200:
                    glyph["fontname"] = font
            with self.subTest(font=font):
                self.assertIs(recover(item, page), item)

    def test_budgets_and_rotation(self):
        item, page = fixture()
        page.rotation = 90
        self.assertIs(recover(item, page), item)
        item, page = fixture()
        page.edges *= 200
        self.assertIs(recover(item, page), item)
        item, page = fixture()
        page.chars *= 1000
        self.assertIs(recover(item, page), item)


if __name__ == "__main__":
    unittest.main()
