import copy
import os
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import pdfplumber
from openpyxl import load_workbook
from pypdf import PdfWriter
from pypdf.generic import RectangleObject
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from source_leaders import recover


def compact(text):
    return "".join(text.split())


class LeaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def fixture(
        self,
        rows=3,
        dots=(90, 96, 102, 108),
        right_dot=114,
        number_x=160,
        border=False,
        crop=False,
        font="Helvetica",
    ):
        path = self.root / "leaders.pdf"
        c = canvas.Canvas(str(path), pagesize=(300, 300))
        cells = []
        values = ("12.5", "08.6", "17.9")
        for row in range(rows):
            y = 240 - row * 30
            c.setFont("Helvetica", 10)
            c.drawString(30, y, "Item")
            for x in dots:
                c.drawString(x, y, ".")
            c.setFont(font, 10)
            c.drawString(right_dot, y, ".")
            c.setFont("Helvetica", 10)
            value = values[row % len(values)]
            c.drawString(number_x, y, value)
            if border:
                c.line(112, y - 5, 112, y + 12)
            top, bottom = 300 - y - 7.93, 300 - y + 2.07
            cells.extend(
                [
                    {
                        "r": row,
                        "c": 0,
                        "rs": 1,
                        "cs": 1,
                        "text": "Item " + " ".join("." for _ in dots),
                        "sourceTextCandidate": [
                            30,
                            top,
                            dots[-1] + stringWidth(".", "Helvetica", 10),
                            bottom,
                        ],
                    },
                    {
                        "r": row,
                        "c": 1,
                        "rs": 1,
                        "cs": 1,
                        "text": ". " + value,
                        "sourceTextCandidate": [
                            right_dot,
                            top,
                            number_x + stringWidth(value, "Helvetica", 10),
                            bottom,
                        ],
                    },
                ]
            )
        c.save()
        if crop:
            writer = PdfWriter(clone_from=path)
            writer.pages[0].cropbox = RectangleObject((35, 0, 300, 300))
            path = self.root / "cropped.pdf"
            writer.write(path)
        doc = pdfplumber.open(path)
        self.addCleanup(doc.close)
        return {
            "method": "layout",
            "cells": cells,
            "widths": [130, 60],
            "heights": [30] * rows,
        }, doc.pages[0]

    def test_recovered_boundary_uses_only_bounded_verified_whitespace(self):
        from layout_typography import refine_widths

        table = {"bbox": [0, 0, 140, 40], "widths": [80, 60], "cells": []}
        for row in range(3):
            table["cells"].extend(
                [
                    {
                        "r": row,
                        "c": 0,
                        "cs": 1,
                        "sourceFont": True,
                        "sourceTextBox": [0, row * 10, 94, row * 10 + 8],
                    },
                    {
                        "r": row,
                        "c": 1,
                        "cs": 1,
                        "sourceFont": True,
                        "sourceTextBox": [110, row * 10, 135, row * 10 + 8],
                    },
                ]
            )
        untouched = copy.deepcopy(table)
        refine_widths(untouched)
        self.assertEqual(untouched["widths"], [80, 60])
        table["sourceLeaderBoundary"] = True
        refined = copy.deepcopy(table)
        refine_widths(refined)
        self.assertEqual(refined["widths"], [98, 42])
        for cell in table["cells"]:
            if cell["c"] == 0:
                cell["sourceTextBox"][2] = 100
        refine_widths(table)
        self.assertEqual(table["widths"], [80, 60])
        for cell in table["cells"]:
            if cell["c"] == 0:
                cell["sourceTextBox"][2] = 20
            else:
                cell["sourceTextBox"][0] = 40
        refine_widths(table)
        self.assertEqual(table["widths"], [80, 60])

    def test_conversion_pipeline_preserves_numbers_and_reports_recovery(self):
        from convert import convert

        table, _page = self.fixture()
        output = self.root / "output.xlsx"
        with (
            patch.dict(os.environ, {"PDF_EXCEL_MODELS": "mock-models"}),
            patch("convert.extract_layout_tables", return_value={0: [table]}),
        ):
            result = convert(self.root / "leaders.pdf", output, {"ocr": False})
        book = load_workbook(output)
        try:
            self.assertEqual(
                [row[1] for row in book.active.values], ["12.5", "08.6", "17.9"]
            )
            self.assertEqual(
                [row[0].count(".") for row in book.active.values], [5, 5, 5]
            )
            self.assertTrue(
                any("dot-leader" in message for message in result["warnings"])
            )
        finally:
            book.close()

    def test_three_rows_transfer_only_existing_dot_and_correct_bounds(self):
        table, page = self.fixture()
        original = copy.deepcopy(table)
        output = recover(table, page)
        self.assertIsNot(output, table)
        self.assertEqual(table, original)
        self.assertEqual(
            Counter(compact("".join(c["text"] for c in table["cells"]))),
            Counter(compact("".join(c["text"] for c in output["cells"]))),
        )
        for row in range(3):
            left, right = output["cells"][row * 2 : row * 2 + 2]
            self.assertEqual(left["text"], "Item . . . . .")
            self.assertEqual(right["text"], ("12.5", "08.6", "17.9")[row])
            self.assertGreater(
                left["sourceTextCandidate"][2],
                table["cells"][row * 2]["sourceTextCandidate"][2],
            )
            self.assertEqual(right["sourceTextCandidate"][0], 160)

    def test_one_or_two_rows_are_not_enough_evidence(self):
        for rows in (1, 2):
            table, page = self.fixture(rows=rows)
            self.assertIs(recover(table, page), table)

    def test_legitimate_leading_decimal_is_unchanged(self):
        table, page = self.fixture()
        for cell in table["cells"]:
            if cell["c"] == 1:
                cell["text"] = ".18"
        self.assertIs(recover(table, page), table)
        for cell in table["cells"]:
            if cell["c"] == 1:
                cell["text"] = ". 18"
        self.assertIs(recover(table, page), table)

    def test_physical_border_blocks_transfer(self):
        table, page = self.fixture(border=True)
        self.assertIs(recover(table, page), table)

    def test_irregular_or_small_gap_and_separate_punctuation_are_unchanged(self):
        for options in (
            {"dots": (90, 96, 103, 108)},
            {"right_dot": 111.1},
            {"right_dot": 144, "number_x": 180},
            {"number_x": 118},
            {"font": "Courier"},
        ):
            with self.subTest(options=options):
                table, page = self.fixture(**options)
                self.assertIs(recover(table, page), table)

    def test_hidden_crop_glyphs_are_not_reintroduced(self):
        table, page = self.fixture(crop=True)
        self.assertIs(recover(table, page), table)

    def test_multiline_merged_mismatched_and_nonfinite_candidates_are_rejected(self):
        for kind in ("multiline", "merged", "mismatch", "nonfinite", "overlap"):
            table, page = self.fixture()
            for cell in table["cells"]:
                if kind == "multiline":
                    cell["text"] += "\n"
                elif kind == "merged":
                    cell["rs"] = 2
                elif kind == "mismatch":
                    cell["text"] += "X"
                elif kind == "nonfinite":
                    cell["sourceTextCandidate"][0] = float("nan")
                elif kind == "overlap" and cell["c"] == 1:
                    cell["sourceTextCandidate"][0] = 109
            with self.subTest(kind=kind):
                self.assertIs(recover(table, page), table)

    def test_one_bad_row_cannot_reach_consensus(self):
        table, page = self.fixture()
        table["cells"][0]["text"] += "X"
        self.assertIs(recover(table, page), table)

    def test_rotated_or_non_native_table_is_unchanged(self):
        table, page = self.fixture()
        table["method"] = "ocr-layout"
        self.assertIs(recover(table, page), table)
        table["method"] = "layout"
        page.rotation = 90
        self.assertIs(recover(table, page), table)

    def test_nonfinite_native_glyph_or_skewed_matrix_is_not_used(self):
        for kind in ("coordinate", "matrix"):
            table, page = self.fixture()
            char = next(c for c in page.chars if c["text"] == "I")
            if kind == "coordinate":
                char["x0"] = float("inf")
            else:
                char["matrix"] = (1, 0.2, 0, 1, 0, 0)
            with self.subTest(kind=kind):
                self.assertIs(recover(table, page), table)


if __name__ == "__main__":
    unittest.main()
