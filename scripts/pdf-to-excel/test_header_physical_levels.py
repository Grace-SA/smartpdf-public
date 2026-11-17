"""Original source-backed fixtures for thick-rule header normalization."""

import copy
import io
import sys
import unittest
from pathlib import Path

import pdfplumber
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_header_tree import recover
from layout_tables import local_box


def fixture(kind="normal"):
    stream = io.BytesIO()
    c = canvas.Canvas(stream, pagesize=(420, 400))
    c.setFont("Helvetica", 10)
    header = [
        (270, 365, "Amounts"),
        (175, 365, "Percent"),
        (185, 340, "who"),
        (170, 325, "borrowed"),
        (30, 325, "Institution characteristics"),
        (250, 340, "North"),
        (330, 340, "South"),
        (250, 325, "value"),
        (330, 325, "total"),
    ]
    for x, y, text in header:
        c.drawString(x, y, text)
    c.line(20, 380, 395, 380)
    c.line(20, 310, 395, 310)
    c.line(235, 350, 395, 350)
    if kind == "separate":
        c.line(235, 349, 395, 349)
    elif kind != "absent":
        c.rect(
            239 if kind == "shifted" else 235,
            349,
            156 if kind == "shifted" else 160,
            1,
            stroke=0,
            fill=1,
        )
    if kind in ("between", "overlapping-glyph"):
        c.setFont("Helvetica", 0.5 if kind == "between" else 3)
        c.drawString(275, 349.4 if kind == "between" else 349.9, "X")
        c.setFont("Helvetica", 10)
    for row in range(4):
        for x, text in (
            (30, f"Item{row}"),
            (180, str(100 + row)),
            (255, str(200 + row)),
            (335, str(300 + row)),
        ):
            c.drawString(x, 290 - row * 20, text)
    c.save()
    stream.seek(0)
    doc = pdfplumber.open(stream)
    page = doc.pages[0]
    words = page.extract_words()
    cells = []

    def add(row, col, text, tokens, rs=1, cs=1):
        ws = [w for w in words if w["text"] in tokens]
        box = [
            min(w["x0"] for w in ws),
            min(w["top"] for w in ws),
            max(w["x1"] for w in ws),
            max(w["bottom"] for w in ws),
        ]
        cells.append(
            {
                "start_row_offset_idx": row,
                "end_row_offset_idx": row + rs,
                "start_col_offset_idx": col,
                "end_col_offset_idx": col + cs,
                "row_span": rs,
                "col_span": cs,
                "text": text,
                "bbox": local_box(box, page),
                "column_header": row < 3,
            }
        )

    add(0, 0, "Institution characteristics", ["Institution", "characteristics"], rs=3)
    add(0, 1, "Percent", ["Percent"])
    add(1, 1, "who", ["who"])
    add(2, 1, "borrowed", ["borrowed"])
    add(0, 2, "Amounts", ["Amounts"], cs=2)
    add(1, 2, "North South", ["North", "South"], cs=2)
    add(2, 2, "value", ["value"])
    add(2, 3, "total", ["total"])
    for row in range(4):
        for col, text in enumerate(
            (f"Item{row}", str(100 + row), str(200 + row), str(300 + row))
        ):
            add(row + 3, col, text, [text])
    return (
        doc,
        page,
        {
            "prov": [{"bbox": local_box([20, 20, 395, 180], page)}],
            "data": {"num_rows": 7, "num_cols": 4, "table_cells": cells},
        },
    )


class PhysicalHeaderTests(unittest.TestCase):
    def source(self, kind="normal"):
        doc, page, item = fixture(kind)
        self.addCleanup(doc.close)
        return page, item

    def test_thick_rule_compression_preserves_body_and_source(self):
        page, item = self.source()
        prior = copy.deepcopy(item)
        out = recover(item, page)
        self.assertIsNot(out, item)
        self.assertEqual(item, prior)
        self.assertEqual(out["data"]["num_rows"], 6)
        headers = {
            (c["start_row_offset_idx"], c["start_col_offset_idx"]): c
            for c in out["data"]["table_cells"]
            if c.get("column_header")
        }
        self.assertEqual(headers[0, 1]["text"], "Percent\nwho\nborrowed")
        self.assertEqual(headers[0, 1]["row_span"], 2)
        self.assertEqual(headers[1, 2]["text"], "North\nvalue")
        self.assertEqual(headers[1, 3]["text"], "South\ntotal")
        body = copy.deepcopy(
            [c for c in out["data"]["table_cells"] if not c.get("column_header")]
        )
        for cell in body:
            cell["start_row_offset_idx"] += 1
            cell["end_row_offset_idx"] += 1
        self.assertEqual(
            body, [c for c in item["data"]["table_cells"] if not c.get("column_header")]
        )

    def test_unproven_rule_pairs_do_not_compress(self):
        for kind in ("separate", "absent", "shifted", "between", "overlapping-glyph"):
            with self.subTest(kind=kind):
                page, item = self.source(kind)
                self.assertIs(recover(item, page), item)

    def test_crossing_cell_ambiguous_stub_and_character_loss_reject(self):
        for kind in ("crossing", "stub", "loss", "leaf"):
            page, item = self.source()
            cells = item["data"]["table_cells"]
            if kind == "crossing":
                cells[0]["end_row_offset_idx"] = 4
                cells[0]["row_span"] = 4
            elif kind == "stub":
                cells.append(copy.deepcopy(cells[0]))
            elif kind == "loss":
                cells[1]["text"] = "Missing"
            else:
                # Same global characters but unmerged wrong-column ownership.
                cells[5]["col_span"] = 1
                cells[5]["end_col_offset_idx"] = 3
            with self.subTest(kind=kind):
                self.assertIs(recover(item, page), item)

    def test_hidden_or_nonfinite_source_not_reconstructed(self):
        for kind in ("crop", "nonfinite"):
            page, item = self.source()
            if kind == "crop":
                page.cropbox = (80, 0, 420, 400)
            else:
                char = next(c for c in page.chars if c["text"] == "I")
                char["x0"] = float("nan")
            with self.subTest(kind=kind):
                self.assertIs(recover(item, page), item)

    def test_excessive_rule_candidates_skip_new_normalization(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        import layout_header_tree as module

        page, item = self.source()
        physical = module.physical_page(page)
        # Many closely spaced matching-span rule pairs must not trigger the
        # new quadratic matching/source-character scan.
        edges = [
            e
            for e in physical.edges
            if e["orientation"] == "h" and (e["top"] < 25 or e["top"] > 85)
        ]
        template = next(
            e for e in physical.edges if e["orientation"] == "h" and 49 < e["top"] < 52
        )
        for i in range(122):
            edge = dict(
                template,
                top=25 + i * 0.48,
                bottom=25 + i * 0.48,
                object_type="line" if i % 2 == 0 else "rect_edge",
            )
            edges.append(edge)

        class CountedChars(list):
            scans = 0

            def __iter__(self):
                self.scans += 1
                return super().__iter__()

        counted = CountedChars(page.chars)
        page.objects["char"] = counted
        original = module.cluster_objects

        def preserve_rule_pairs(objects, key, tolerance):
            # Keep nearby rules individually distinct for the budget fixture;
            # use ordinary grouping for subsequent column-annotated levels.
            if (
                objects
                and isinstance(objects[0], dict)
                and "orientation" in objects[0]
                and "columns" not in objects[0]
            ):
                return [[obj] for obj in objects]
            return original(objects, key, tolerance)

        with (
            patch.object(
                module, "physical_page", return_value=SimpleNamespace(edges=edges)
            ),
            patch.object(module, "cluster_objects", side_effect=preserve_rule_pairs),
        ):
            self.assertIs(recover(item, page), item)
        self.assertEqual(counted.scans, 0)

    def test_two_level_model_not_compressed(self):
        page, item = self.source()
        for cell in item["data"]["table_cells"]:
            if cell.get("column_header"):
                cell["start_row_offset_idx"] = min(cell["start_row_offset_idx"], 1)
                cell["end_row_offset_idx"] = min(cell["end_row_offset_idx"], 2)
                cell["row_span"] = (
                    cell["end_row_offset_idx"] - cell["start_row_offset_idx"]
                )
        self.assertIs(recover(item, page), item)

    def test_genuine_three_levels_retain_existing_behavior(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "old_header_fixture", Path(__file__).with_name("test_header_tree.py")
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        doc, page, item = module.fixture()
        self.addCleanup(doc.close)
        out = recover(item, page)
        self.assertIsNot(out, item)
        self.assertEqual(out["data"]["num_rows"], item["data"]["num_rows"])
        self.assertEqual(
            max(
                c["end_row_offset_idx"]
                for c in out["data"]["table_cells"]
                if c.get("column_header")
            ),
            3,
        )


if __name__ == "__main__":
    unittest.main()
