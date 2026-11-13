"""Adversarial synthetic stroke, clip and blend rendering boundaries."""
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from PIL import ImageChops
import pypdfium2 as pdf
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, DictionaryObject
from model import Rejected
from worker import needs_ocr, convert
from test_worker import fixture
from test_text_transparency import SECRET, HEADING
from test_form_paint_order import form_pdf

CURVE = b'q 1 1 1 RG 8 w 100 745 m 100 750 100 760 100 765 c S Q '
POLYLINE = b'q 1 1 1 RG 8 w 100 745 m 100 755 l 100 765 l S Q '


class ComplexPaintTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root/'synthetic.pdf'

    def tearDown(self):
        self.temp.cleanup()

    def routed(self, content):
        fixture(self.source, content=content)
        with pdf.PdfDocument(self.source) as doc, closing(doc[0]) as page:
            return needs_ocr(page)[0]

    def render(self):
        with pdf.PdfDocument(self.source) as doc, closing(doc[0]) as page:
            with closing(page.render(scale=2)) as bitmap:
                return bitmap.to_pil().convert('RGB').copy()

    def test_curve_and_polyline_change_pixels_and_require_ocr(self):
        fixture(self.source, content=SECRET+HEADING)
        original = self.render()
        for stroke in (CURVE, POLYLINE):
            self.assertTrue(self.routed(SECRET+HEADING+stroke))
            self.assertIsNotNone(ImageChops.difference(original,self.render()).getbbox())

    def test_stroke_background_and_disjoint_counterexamples(self):
        self.assertFalse(self.routed(CURVE+SECRET+HEADING))
        self.assertFalse(self.routed(SECRET+HEADING+b'q 1 0 0 1 300 0 cm '+CURVE+b'Q'))

    def test_thin_rectangle_has_clear_interior_but_thick_outline_does_not(self):
        self.assertFalse(self.routed(SECRET+HEADING+b'q 1 w 40 740 100 30 re S Q'))
        self.assertTrue(self.routed(SECRET+HEADING+b'q 1 1 1 RG 30 w 40 740 100 30 re S Q'))

    def test_filled_rectangle_never_gets_clear_interior_exemption(self):
        self.assertTrue(self.routed(SECRET+HEADING+b'q 1 1 1 rg 40 740 100 30 re B Q'))

    def test_transformed_rectangle_and_curve(self):
        for content, expected in ((b'20 370 50 15 re S',False),
                                  (b'1 1 1 RG 4 w 50 372.5 m 50 375 50 380 50 382.5 c S',True)):
            form_pdf(self.source, inside=content, outside=SECRET+HEADING,
                     matrices=[(2,0,0,2,0,0)])
            with pdf.PdfDocument(self.source) as doc, closing(doc[0]) as page:
                self.assertEqual(needs_ocr(page)[0], expected)

    def test_clipped_stroke_is_conservative_even_if_pixels_unchanged(self):
        fixture(self.source, content=SECRET+HEADING)
        original = self.render()
        # The stroke's bounds intersect text, but clip removes the painted pixels.
        self.assertTrue(self.routed(SECRET+HEADING+b'q 0 0 10 10 re W n '+CURVE+b'Q'))
        self.assertIsNone(ImageChops.difference(original,self.render()).getbbox())

    def test_screen_blended_stroke_requires_ocr(self):
        fixture(self.source, content=SECRET+HEADING+b'q /GS gs '+CURVE+b'Q')
        writer = PdfWriter()
        page = writer.add_page(PdfReader(self.source).pages[0])
        page['/Resources'][NameObject('/ExtGState')] = DictionaryObject({
            NameObject('/GS'): writer._add_object(DictionaryObject({NameObject('/BM'):NameObject('/Screen')}))})
        writer.write(self.source)
        with pdf.PdfDocument(self.source) as doc, closing(doc[0]) as page:
            self.assertTrue(needs_ocr(page)[0])

    def test_no_native_output_for_covered_amount(self):
        fixture(self.source, content=SECRET+HEADING+CURVE)
        output = self.root/'result.docx'
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaisesRegex(Rejected,'OCR worker is not configured'):
                convert(self.source,output)
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
