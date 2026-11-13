import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import load_workbook
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from convert import convert
from source_context import ocr_page_context


def line(text, y=150, score=0.99, x=10):
    return ([[x, y], [x + 90, y], [x + 90, y + 10], [x, y + 10]], text, score)


class ScanContextTests(unittest.TestCase):
    def test_literal_notes_outside_every_table_only(self):
        lines = [
            line("inside", y=20),
            line("second table", y=110),
            line("* N/A", y=170),
            line("00123 =1+1", y=190),
        ]
        text = ocr_page_context(
            lines, [(0, 0, 100, 80), (0, 100, 100, 130)], (300, 300)
        )
        self.assertEqual(text, "* N/A\n00123 =1+1")

    def test_uncertain_skewed_and_invalid_context_are_not_guessed(self):
        for bad in (
            line("uncertain", score=0.84),
            line("bad\ufffe"),
            line("bad", score=float("nan")),
            line("x" * 16001),
        ):
            self.assertEqual(
                ocr_page_context([line("good"), bad], [(0, 0, 100, 80)], (300, 300)), ""
            )
        skew = line("skew")
        skew[0][1][1] += 6
        self.assertEqual(ocr_page_context([skew], [(0, 0, 100, 80)], (300, 300)), "")

    def test_malformed_optional_ocr_context_is_rejected_without_exception(self):
        for lines in (
            [line("bad", score=1.5)],
            [line("bad", score=None)],
            [line("bad", score="not a score")],
            [(None, "bad", 0.9)],
            [([], None, 0.9)],
            [("incomplete",)],
            None,
        ):
            with self.subTest(lines=lines):
                self.assertEqual(
                    ocr_page_context(lines, [(0, 0, 100, 80)], (300, 300)), ""
                )

    def test_cropped_or_table_overlapping_regions_are_not_included(self):
        self.assertEqual(
            ocr_page_context(
                [line("outside image", x=-5), line("crossing table", y=75)],
                [(0, 0, 100, 80)],
                (300, 300),
            ),
            "",
        )

    def test_real_scanned_table_context_is_marked_ocr(self):
        import pypdfium2 as pdfium
        from reportlab.lib.utils import ImageReader

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            native = root / "native.pdf"
            c = canvas.Canvas(str(native), pagesize=(600, 600))
            c.setFont("Helvetica", 14)
            c.drawString(100, 470, "Quarterly results")
            for x in (100, 250, 400):
                c.line(x, 300, x, 420)
            for y in (300, 340, 380, 420):
                c.line(100, y, 400, y)
            for row, values in enumerate(
                (("Code", "Amount"), ("123", "12.50"), ("007", "18.00"))
            ):
                for col, value in enumerate(values):
                    c.drawString(110 + 150 * col, 400 - 40 * row, value)
            c.drawString(100, 265, "Data not available")
            c.save()
            with pdfium.PdfDocument(native) as doc:
                image = doc[0].render(scale=2).to_pil()
            scanned = root / "scan.pdf"
            c = canvas.Canvas(str(scanned), pagesize=(600, 600))
            c.drawImage(ImageReader(image), 0, 0, 600, 600)
            c.save()
            output = root / "scan.xlsx"
            with patch.dict(os.environ, {}, clear=True):
                result = convert(scanned, output, {})
            self.assertEqual(result["ocrPages"], [1])
            book = load_workbook(output)
            try:
                note = book.active["A1"].comment.text
                self.assertIn("OCR text (uncorrected; verify against the scan)", note)
                self.assertIn("Quarterly results", note)
                self.assertIn("Data not available", note)
                self.assertNotIn("12.50", note)
                self.assertFalse(
                    any(c.data_type == "f" for s in book for row in s for c in row)
                )
            finally:
                book.close()


if __name__ == "__main__":
    unittest.main()
