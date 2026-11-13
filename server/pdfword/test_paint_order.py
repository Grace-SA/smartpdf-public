"""Synthetic overlays must not expose covered text as editable source truth."""
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, NumberObject, DictionaryObject, DecodedStreamObject
from docx import Document
from PIL import ImageChops
import pypdfium2 as pdf

from model import Rejected
from test_worker import fixture
from worker import convert, needs_ocr

TEXT = b'BT /F1 12 Tf 48 750 Td (Amount 123.45) Tj ET '
COVER = b'q 1 1 1 rg 100 748 5 15 re f Q '


class PaintOrderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def source(self, content):
        source = self.root / 'synthetic.pdf'
        fixture(source, content=content)
        return source

    def routed(self, content):
        with pdf.PdfDocument(self.source(content)) as doc, closing(doc[0]) as page:
            return needs_ocr(page)[0]

    def test_partial_white_cover_changes_pixels_and_requires_ocr(self):
        images = []
        for content in (TEXT, TEXT + COVER):
            with pdf.PdfDocument(self.source(content)) as doc, closing(doc[0]) as page:
                with closing(page.render(scale=2)) as bitmap:
                    images.append(bitmap.to_pil().convert('RGB').copy())
        self.assertIsNotNone(ImageChops.difference(*images).getbbox())
        self.assertTrue(self.routed(TEXT + COVER))

    def test_complete_black_cover_requires_ocr(self):
        self.assertTrue(self.routed(TEXT + b'0 0 0 rg 40 740 100 30 re f'))

    def test_background_before_text_remains_native(self):
        self.assertFalse(self.routed(COVER + TEXT))

    def test_nonoverlapping_fill_remains_native(self):
        self.assertFalse(self.routed(TEXT + b'0 0 0 rg 100 600 20 20 re f'))

    def test_unfilled_table_border_remains_native(self):
        self.assertFalse(self.routed(TEXT + b'40 740 100 30 re S'))

    def test_missing_ocr_never_returns_covered_amount(self):
        source = self.source(TEXT + COVER)
        output = self.root / 'result.docx'
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaisesRegex(Rejected, 'OCR worker is not configured'):
                convert(source, output)
        self.assertFalse(output.exists())

    def test_ocr_adapter_not_underlying_native_text_is_exported(self):
        source = self.source(TEXT + COVER)
        output = self.root / 'result.docx'
        result = [dict(kind='paragraph', bbox=[48,30,140,50], text='Visible result',
                       source='test', size=12)]
        with patch('worker.OCR.recognize', return_value=result) as recognize:
            report = convert(source, output)
        recognize.assert_called_once()
        self.assertEqual([p.text for p in Document(output).paragraphs], ['Visible result'])
        self.assertTrue(any('recognized with OCR' in w for w in report['warnings']))

    def test_image_overlay_order_and_disjoint_counterexamples(self):
        for before, x, expected in ((False, 100, True), (True, 100, False), (False, 300, False)):
            with self.subTest(before=before, x=x):
                source = self.source(TEXT)
                writer = PdfWriter()
                page = writer.add_page(PdfReader(source).pages[0])
                image = DecodedStreamObject()
                image.set_data(bytes([255, 255, 255]))
                image.update({NameObject('/Type'): NameObject('/XObject'),
                              NameObject('/Subtype'): NameObject('/Image'),
                              NameObject('/Width'): NumberObject(1),
                              NameObject('/Height'): NumberObject(1),
                              NameObject('/ColorSpace'): NameObject('/DeviceRGB'),
                              NameObject('/BitsPerComponent'): NumberObject(8)})
                page['/Resources'][NameObject('/XObject')] = DictionaryObject(
                    {NameObject('/Im'): writer._add_object(image)})
                paint = f'q 5 0 0 15 {x} 748 cm /Im Do Q '.encode()
                content = DecodedStreamObject()
                content.set_data(paint + TEXT if before else TEXT + paint)
                page[NameObject('/Contents')] = writer._add_object(content)
                writer.write(source)
                with pdf.PdfDocument(source) as doc, closing(doc[0]) as rendered:
                    self.assertEqual(needs_ocr(rendered)[0], expected)

    def test_overlap_work_is_bounded(self):
        # Many disjoint text and paint objects cannot cause quadratic unbounded work.
        text = b''.join(f'BT /F1 8 Tf 48 {100+i} Td (Row {i}) Tj ET '.encode() for i in range(320))
        fills = b''.join(f'q 0 0 0 rg {300+i/10} 600 20 20 re f Q '.encode() for i in range(320))
        self.assertTrue(self.routed(text + fills))


if __name__ == '__main__':
    unittest.main()
