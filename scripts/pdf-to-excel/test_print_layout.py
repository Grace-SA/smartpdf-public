"""Verify workbook print layout from contrasting real PDF page geometries."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from reportlab.pdfgen import canvas
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from convert import convert


def source(path, landscape_first=False):
    pdf = canvas.Canvas(str(path))
    sizes = [(600, 800), (800, 600)]
    if landscape_first:
        sizes.reverse()
    for width, height in sizes:
        pdf.setPageSize((width, height))
        # A wide portrait table and narrow landscape table defeat width guesses.
        xs = [30, 300, 570] if width < height else [30, 140, 250]
        for x in xs:
            pdf.line(x, 100, x, 180)
        for y in [100, 140, 180]:
            pdf.line(xs[0], y, xs[-1], y)
        pdf.setFont("Helvetica", 10)
        for x, y, text in [
            (xs[0] + 4, 160, "Label"),
            (xs[1] + 4, 160, "Value"),
            (xs[0] + 4, 120, "Portrait" if width < height else "Landscape"),
            (xs[1] + 4, 120, "00123"),
        ]:
            pdf.drawString(x, y, text)
        pdf.showPage()
    pdf.save()


class PrintLayoutTests(unittest.TestCase):
    def test_separate_tables_use_source_orientation_and_one_printed_page(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {}, clear=True
        ):
            root = Path(folder)
            src = root / "pages.pdf"
            out = root / "result.xlsx"
            source(src)
            result = convert(src, out, {})
            self.assertEqual(result["tables"], 2)
            book = load_workbook(out)
            try:
                self.assertEqual(
                    [s.page_setup.orientation for s in book], ["portrait", "landscape"]
                )
                for s in book:
                    self.assertEqual(s["B2"].value, "00123")
                    self.assertEqual(
                        (s.page_setup.fitToWidth, s.page_setup.fitToHeight), (1, 1)
                    )
            finally:
                book.close()

    def test_shared_sheet_retains_landscape_in_both_page_orders(self):
        for landscape_first in [False, True]:
            with self.subTest(
                landscape_first=landscape_first
            ), tempfile.TemporaryDirectory() as folder, patch.dict(
                os.environ, {}, clear=True
            ):
                root = Path(folder)
                src = root / "pages.pdf"
                out = root / "result.xlsx"
                source(src, landscape_first)
                convert(src, out, {"layout": "single"})
                book = load_workbook(out)
                try:
                    self.assertEqual(book.active.page_setup.orientation, "landscape")
                    self.assertEqual(book.active.page_setup.fitToHeight, 0)
                    values = [
                        v for row in book.active.values for v in row if v is not None
                    ]
                    self.assertEqual(values.count("00123"), 2)
                finally:
                    book.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
