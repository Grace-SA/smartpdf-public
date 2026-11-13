"""Original full-width native section fixtures; no public sample identifiers."""

import copy
import io
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import pdfplumber
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_native_colspans import recover


def fixture(split=None):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(400, 300))
    c.setFont("Helvetica", 10)
    specs = []
    for r in range(5):
        for col in range(3):
            if r == 1 and col:
                continue
            text = (
                "Section label"
                if r == 1
                else (f"Header{col}" if r == 0 else f"{r}.{col}00")
            )
            specs.append((r, col, text, 35 + col * 100, 246 - r * 20))
    for _, _, text, x, y in specs:
        c.drawString(x, y, text)
    for y in range(160, 261, 20):
        c.line(30, y, 330, y)
    for x in [30, 330]:
        c.line(x, 160, x, 260)
    for x in [130, 230]:
        c.line(x, 160, x, 220)
        c.line(x, 240, x, 260)
    if split is not None:
        c.line(split, 220, split, 240)
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
        gs = [g for g in chars if g["matrix"][5] == y and x <= g["x0"] < x + 90]
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
                "row_span": 1,
                "col_span": 1,
                "start_row_offset_idx": r,
                "end_row_offset_idx": r + 1,
                "start_col_offset_idx": col,
                "end_col_offset_idx": col + 1,
                "column_header": r == 0,
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
    return {"data": {"num_rows": 5, "num_cols": 3, "table_cells": cells}}, page


class NativeColspanTests(unittest.TestCase):
    def test_exact_span_only_change(self):
        item, page = fixture()
        before = copy.deepcopy(item)
        out = recover(item, page)
        self.assertIsNot(out, item)
        expected = copy.deepcopy(item)
        expected["data"]["table_cells"][3].update(col_span=3, end_col_offset_idx=3)
        self.assertEqual(out, expected)
        self.assertEqual(item, before)

    def test_empty_slots_removed_but_real_value_blocks(self):
        for text in ["", "9"]:
            item, page = fixture()
            extra = copy.deepcopy(item["data"]["table_cells"][3])
            extra.update(text=text, start_col_offset_idx=1, end_col_offset_idx=2)
            item["data"]["table_cells"].append(extra)
            out = recover(item, page)
            if text:
                self.assertIs(out, item)
            else:
                self.assertEqual(
                    len(out["data"]["table_cells"]),
                    len(item["data"]["table_cells"]) - 1,
                )

    def test_open_border_and_partial_interior_rule(self):
        item, page = fixture()
        page.edges = [e for e in page.edges if not (e["x0"] == e["x1"] == 330)]
        self.assertIs(recover(item, page), item)
        item, page = fixture()
        page.edges.append(
            {"x0": 130, "x1": 130, "top": 65, "bottom": 72, "orientation": "v"}
        )
        self.assertIs(recover(item, page), item)

    def test_annotation_image_unknown_and_crop(self):
        for attr in ["annots", "images"]:
            for value in [
                {},
                {"x0": float("nan"), "x1": 80, "top": 60, "bottom": 80},
                {
                    "x0": 40,
                    "x1": 80,
                    "top": 60,
                    "bottom": 80,
                    "contents": "",
                    "data": {"AP": {}},
                },
            ]:
                item, page = fixture()
                setattr(page, attr, [value])
                self.assertIs(recover(item, page), item)
        item, page = fixture()
        page.cropbox = (31, 0, 400, 300)
        self.assertIs(recover(item, page), item)
        item, page = fixture()
        page.images = [{"x0": 1, "x1": 10, "top": 1, "bottom": 10}]
        self.assertIsNot(recover(item, page), item)

    def test_metadata_source_and_bounds(self):
        for key, value in [
            ("row_span", True),
            ("end_row_offset_idx", 4),
            ("start_row_offset_idx", -1),
            ("text", "Other label"),
        ]:
            item, page = fixture()
            item["data"]["table_cells"][3][key] = value
            self.assertIs(recover(item, page), item)
        item, page = fixture()
        item["data"]["table_cells"].append(
            copy.deepcopy(item["data"]["table_cells"][3])
        )
        self.assertIs(recover(item, page), item)
        item, page = fixture()
        page.edges.append({})
        self.assertIs(recover(item, page), item)
        item, page = fixture()
        g = copy.deepcopy(page.chars[0])
        g.update(x0=200, x1=210, top=65, bottom=75, text="X")
        page.chars.append(g)
        self.assertIs(recover(item, page), item)
        item, page = fixture()
        page.find_tables = lambda: (_ for _ in ()).throw(ValueError("bad finder"))
        self.assertIs(recover(item, page), item)

    def test_shifted_full_width_with_adjacent_blank_cell_rejected(self):
        for split, keep_left in [(240, True), (32, False)]:
            item, page = fixture()
            table = page.find_tables()[0]
            for i, b in enumerate(table.cells):
                if b[0] == 30 and b[2] == 330:
                    left = (b[0], b[1], split, b[3])
                    right = (split, b[1], b[2], b[3])
                    table.cells[i] = left if keep_left else right
                    table.cells.append(right if keep_left else left)
                    page.edges.append(
                        {
                            "x0": split,
                            "x1": split,
                            "top": b[1],
                            "bottom": b[3],
                            "orientation": "v",
                        }
                    )
                    break
            self.assertIs(recover(item, page), item)

    def test_real_pdf_adjacent_blank_physical_cell(self):
        for split in (240, 32):
            item, page = fixture(split=split)
            self.assertIs(recover(item, page), item)

    def test_repeated_model_boxes_are_not_distinct_source_evidence(self):
        item, page = fixture()
        # Three different model row indices all point at one physical source row.
        for col in range(3):
            repeated = next(
                c["bbox"]
                for c in item["data"]["table_cells"]
                if c["start_row_offset_idx"] == 2 and c["start_col_offset_idx"] == col
            )
            for cell in item["data"]["table_cells"]:
                if (
                    cell["start_row_offset_idx"] in (3, 4)
                    and cell["start_col_offset_idx"] == col
                ):
                    cell["bbox"] = copy.deepcopy(repeated)
        self.assertIs(recover(item, page), item)

    def test_no_eligible_rows_skip_finder(self):
        for filled in (False, True):
            item, page = fixture()
            if filled:
                extra = copy.deepcopy(item["data"]["table_cells"][3])
                extra.update(text="9", start_col_offset_idx=1, end_col_offset_idx=2)
                item["data"]["table_cells"].append(extra)
            else:
                item["data"]["table_cells"] = [
                    c
                    for c in item["data"]["table_cells"]
                    if c["start_row_offset_idx"] != 1
                ]
            calls = []

            def finder(calls=calls):
                calls.append(True)
                raise AssertionError("ineligible tables must not reach finder")

            page.find_tables = finder
            self.assertIs(recover(item, page), item)
            self.assertEqual(calls, [])

    def test_intersection_budget_before_finder(self):
        item, page = fixture()
        calls = []

        def finder():
            calls.append(True)
            raise AssertionError("must not run")

        page.find_tables = finder
        page.edges = [
            {"x0": 0, "x1": 2000, "top": i * 2, "bottom": i * 2, "orientation": "h"}
            for i in range(101)
        ] + [
            {"x0": i * 2, "x1": i * 2, "top": 0, "bottom": 2000, "orientation": "v"}
            for i in range(101)
        ]
        self.assertIs(recover(item, page), item)
        self.assertEqual(calls, [])
        page.edges *= 30
        self.assertIs(recover(item, page), item)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
