import copy
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import pdfplumber
from pypdf import PdfWriter
from pypdf.generic import RectangleObject
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_local_sections import recover


def compact(text):
    return "".join(text.split())


class LocalSectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def fixture(
        self,
        border=False,
        extra=False,
        wrapped=False,
        top_values=False,
        crop=False,
        extra_shift=0,
        reference_extra=None,
    ):
        path = self.root / "sections.pdf"
        c = canvas.Canvas(str(path), pagesize=(450, 700))
        c.setFont("Helvetica", 10)
        cells = []

        def cell(row, col, text, x, y, header=False):
            c.drawString(x, y, text)
            box = {
                "l": x,
                "t": 700 - y - 7.93,
                "r": x + stringWidth(text, "Helvetica", 10),
                "b": 700 - y + 2.07,
                "coord_origin": "TOPLEFT",
            }
            data = {
                "start_row_offset_idx": row,
                "end_row_offset_idx": row + 1,
                "start_col_offset_idx": col,
                "end_col_offset_idx": col + 1,
                "row_span": 1,
                "col_span": 1,
                "text": text,
                "bbox": box,
                "column_header": header,
                "row_header": col == 0,
                "row_section": False,
            }
            cells.append(data)
            return data

        def record(row, text, y):
            cell(row, 0, text, 45, y)
            cell(row, 1, "12.5", 260, y)
            cell(row, 2, "2,100", 350, y)

        cell(0, 0, "Group", 40, 650, True)
        cell(0, 1, "Rate", 260, 650, True)
        cell(0, 2, "Count", 350, 650, True)
        record(1, "First", 620)
        head = cell(2, 0, "Category One", 45 if wrapped else 40, 598)
        child = cell(2, 0, "Second", 45, 586)
        cells.remove(child)
        head["text"] += " " + child["text"]
        head["bbox"]["r"] = max(head["bbox"]["r"], child["bbox"]["r"])
        head["bbox"]["b"] = child["bbox"]["b"]
        cell(2, 1, "08.6", 260, 598 if top_values else 586)
        cell(2, 2, "1,200", 350, 598 if top_values else 586)
        record(3, "Third", 574)
        cell(4, 0, "Category Two", 40, 552)
        record(5, "Fourth", 540)
        record(6, "Fifth", 528)
        cell(7, 0, "Category Three", 40, 506)
        record(8, "Sixth", 494)
        record(9, "Seventh", 482)
        if border:
            c.line(250, 580, 250, 610)
        if extra:
            c.drawString(350, 598 + extra_shift, "17")
        if reference_extra is not None:
            for y in (552, 506):
                c.drawString(260, y + reference_extra, "99.9")
                c.drawString(350, y + reference_extra, "9,999")
        c.save()
        if crop:
            writer = PdfWriter(clone_from=path)
            writer.pages[0].cropbox = RectangleObject((42, 0, 450, 700))
            path = self.root / "crop.pdf"
            writer.write(path)
        doc = pdfplumber.open(path)
        self.addCleanup(doc.close)
        item = {
            "prov": [
                {
                    "bbox": {
                        "l": 40,
                        "t": 40,
                        "r": 400,
                        "b": 230,
                        "coord_origin": "TOPLEFT",
                    }
                }
            ],
            "data": {"num_rows": 10, "num_cols": 3, "table_cells": cells},
        }
        return item, doc.pages[0]

    def test_local_split_preserves_glyphs_values_and_original(self):
        item, page = self.fixture()
        before = copy.deepcopy(item)
        out = recover(item, page)
        self.assertIsNot(out, item)
        self.assertEqual(item, before)
        self.assertEqual(out["data"]["num_rows"], 11)
        old, new = item["data"]["table_cells"], out["data"]["table_cells"]
        self.assertEqual(
            Counter(compact("".join(c["text"] for c in old))),
            Counter(compact("".join(c["text"] for c in new))),
        )
        indexed = {
            (c["start_row_offset_idx"], c["start_col_offset_idx"]): c for c in new
        }
        self.assertEqual(indexed[2, 0]["text"], "Category One")
        self.assertEqual(indexed[3, 0]["text"], "Second")
        self.assertEqual(indexed[3, 1]["text"], "08.6")
        self.assertEqual(indexed[3, 2]["text"], "1,200")
        self.assertFalse(
            any(
                c["start_row_offset_idx"] == 2 and c["start_col_offset_idx"] > 0
                for c in new
            )
        )
        for c in old:
            if c["start_row_offset_idx"] == 2 and c["start_col_offset_idx"] == 0:
                continue
            target = copy.deepcopy(c)
            if target["start_row_offset_idx"] >= 2:
                target["start_row_offset_idx"] += 1
                target["end_row_offset_idx"] += 1
            self.assertIn(target, new)

    def test_insufficient_same_table_section_evidence_is_unchanged(self):
        item, page = self.fixture()
        item["data"]["table_cells"] = [
            c for c in item["data"]["table_cells"] if c["start_row_offset_idx"] != 7
        ]
        self.assertIs(recover(item, page), item)

    def test_wrapped_record_or_top_aligned_values_are_not_split(self):
        for options in ({"wrapped": True}, {"top_values": True}):
            item, page = self.fixture(**options)
            self.assertIs(recover(item, page), item)

    def test_physical_closed_cell_and_omitted_upper_values_block_split(self):
        for options in ({"border": True}, {"extra": True}):
            item, page = self.fixture(**options)
            self.assertIs(recover(item, page), item)

    def test_merged_cell_crossing_insert_point_blocks_split(self):
        item, page = self.fixture()
        crossing = item["data"]["table_cells"][0]
        crossing.update(end_row_offset_idx=3, row_span=3)
        self.assertIs(recover(item, page), item)

    def test_shifted_unmodelled_digit_overlapping_section_band_blocks_split(self):
        for shift in (-7, -3, 3, 7):
            item, page = self.fixture(extra=True, extra_shift=shift)
            with self.subTest(shift=shift):
                self.assertIs(recover(item, page), item)

    def test_unmodelled_reference_values_do_not_become_section_evidence(self):
        for shift in (0, -3, 3):
            item, page = self.fixture(reference_extra=shift)
            with self.subTest(shift=shift):
                self.assertIs(recover(item, page), item)

    def test_invalid_model_dimensions_coordinates_and_duplicates_are_rejected(self):
        for kind in (
            "too_many",
            "duplicate",
            "negative",
            "out_of_range",
            "span",
            "type",
        ):
            item, page = self.fixture()
            cells = item["data"]["table_cells"]
            if kind == "too_many":
                item["data"]["table_cells"] = cells * 2
            elif kind == "duplicate":
                cells.append(copy.deepcopy(cells[0]))
            elif kind == "negative":
                cells[0]["start_row_offset_idx"] = -1
            elif kind == "out_of_range":
                cells[0]["end_col_offset_idx"] = 4
            elif kind == "span":
                cells[0]["row_span"] = 2
            else:
                cells[0]["start_row_offset_idx"] = "0"
            with self.subTest(kind=kind):
                self.assertIs(recover(item, page), item)

    def test_missing_mismatched_or_nonfinite_source_evidence_is_unchanged(self):
        for kind in ("text", "box", "matrix"):
            item, page = self.fixture()
            target = next(
                c
                for c in item["data"]["table_cells"]
                if c["start_row_offset_idx"] == 2 and c["start_col_offset_idx"] == 0
            )
            if kind == "text":
                target["text"] += " invented"
            elif kind == "box":
                target["bbox"]["l"] = float("nan")
            else:
                glyph = next(
                    c for c in page.chars if c["text"] == "C" and 90 < c["top"] < 105
                )
                glyph["matrix"] = (1, 0.2, 0, 1, 0, 0)
            with self.subTest(kind=kind):
                self.assertIs(recover(item, page), item)

    def test_crop_or_rotation_does_not_reintroduce_hidden_text(self):
        item, page = self.fixture(crop=True)
        self.assertIs(recover(item, page), item)
        item, page = self.fixture()
        page.rotation = 90
        self.assertIs(recover(item, page), item)

    def test_row_indices_can_shift_without_changing_decision(self):
        item, page = self.fixture()
        for c in item["data"]["table_cells"]:
            c["start_row_offset_idx"] += 1
            c["end_row_offset_idx"] += 1
        item["data"]["num_rows"] += 1
        out = recover(item, page)
        self.assertEqual(out["data"]["num_rows"], 12)
        self.assertEqual(
            next(
                c["text"]
                for c in out["data"]["table_cells"]
                if c["start_row_offset_idx"] == 3 and c["start_col_offset_idx"] == 0
            ),
            "Category One",
        )


if __name__ == "__main__":
    unittest.main()
