import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pdfplumber
from openpyxl import load_workbook
from pypdf import PdfWriter
from pypdf.generic import RectangleObject
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from convert import convert
from source_context import page_context


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def source(self, mixed=False, crop=False, pages=1):
        source = self.root / "source.pdf"
        c = canvas.Canvas(str(source), pagesize=(600, 600))
        for i in range(pages):
            c.setFont("Helvetica", 10)
            c.drawString(100, 470, f"Results page {i + 1}")
            for x in (100, 250, 400):
                c.line(x, 300, x, 420)
            for y in (300, 340, 380, 420):
                c.line(100, y, 400, y)
            for row, values in enumerate(
                (("Code", "Amount"), ("00123", "12.50*"), ("00007", "-12.00"))
            ):
                for col, value in enumerate(values):
                    c.drawString(110 + 150 * col, 400 - 40 * row, value)
            c.drawString(100, 270, "* Data not available")
            c.drawString(100, 250, '=HYPERLINK("https://example.invalid")')
            c.drawString(10, 550, "HIDDEN SECRET")
            if mixed:
                c.saveState()
                c.translate(460, 300)
                c.rotate(90)
                c.drawString(0, 0, "VERTICAL LEGEND")
                c.restoreState()
            c.showPage()
        c.save()
        if crop:
            writer = PdfWriter(clone_from=source)
            for page in writer.pages:
                page.cropbox = RectangleObject((80, 200, 500, 500))
            writer.write(self.root / "cropped.pdf")
            source = self.root / "cropped.pdf"
        return source

    def test_context_comments_preserve_notes_not_formula_in_both_layouts(self):
        for layout in ("tables", "single"):
            source = self.source(crop=True, pages=2)
            before = source.read_bytes()
            out = self.root / "out.xlsx"
            with patch.dict(os.environ, {}, clear=True):
                result = convert(source, out, {"layout": layout})
            book = load_workbook(out)
            comments = [
                c.comment.text
                for sheet in book
                for row in sheet
                for c in row
                if c.comment
            ]
            self.assertEqual(len(comments), 2)
            for i, note in enumerate(comments):
                self.assertIn(f"Source page {i + 1}", note)
                self.assertIn("* Data not available", note)
                self.assertIn('=HYPERLINK("https://example.invalid")', note)
                self.assertNotIn("HIDDEN SECRET", note)
                self.assertNotIn("00123", note)
            self.assertFalse(
                any(c.data_type == "f" for sheet in book for row in sheet for c in row)
            )
            self.assertTrue(any("comment" in w for w in result["warnings"]))
            self.assertEqual(source.read_bytes(), before)
            book.close()

    def test_unknown_boundaries_and_mixed_context_are_not_guessed(self):
        with pdfplumber.open(self.source(mixed=True)) as doc:
            page = doc.pages[0]
            self.assertEqual(page_context(page, [{}]), "")
            self.assertEqual(page_context(page, [{"bbox": (100, 180, 400, 300)}]), "")

    def test_xml_incompatible_and_over_budget_context_is_not_exported(self):
        from unittest.mock import MagicMock

        page = MagicMock()
        page.bbox = (0, 0, 600, 600)
        page.cropbox = None
        page.mediabox = page.bbox
        page.filter.return_value.chars = [
            {"text": "a", "matrix": (1, 0, 0, 1, 0, 0)}
        ] * 10
        for note in ("bad\ufffe", "bad\uffff", "bad\ud800", "bad\x00", "x" * 16001):
            page.filter.return_value.extract_text.return_value = note
            with self.subTest(note=repr(note[:20])):
                self.assertEqual(
                    page_context(page, [{"bbox": (100, 100, 200, 200)}]), ""
                )

    def test_all_table_boundaries_are_excluded(self):
        with pdfplumber.open(self.source(crop=True)) as doc:
            text = page_context(
                doc.pages[0],
                [
                    {"bbox": (100, 180, 400, 300)},
                    {"bbox": (90, 310, 410, 360)},
                ],
            )
            self.assertIn("Results page 1", text)
            self.assertNotIn("Data not available", text)
            self.assertNotIn("HYPERLINK", text)
            self.assertNotIn("00123", text)
            self.assertNotIn("HIDDEN SECRET", text)

    def test_short_note_is_retained(self):
        path = self.root / "short.pdf"
        c = canvas.Canvas(str(path))
        c.drawString(100, 100, "* N/A")
        c.save()
        with pdfplumber.open(path) as doc:
            self.assertEqual(
                page_context(doc.pages[0], [{"bbox": (0, 0, 200, 200)}]), "* N/A"
            )


if __name__ == "__main__":
    unittest.main()
