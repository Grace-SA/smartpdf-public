"""Synthetic soft masks must not leak hidden source text into editable Word."""
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from docx import Document
from PIL import ImageChops
import pypdfium2 as pdf
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (NameObject, DictionaryObject, DecodedStreamObject,
                           RectangleObject)

from model import Rejected
from test_worker import fixture
from worker import convert, needs_ocr

HEADING = b'BT /F1 12 Tf 48 700 Td (Visible heading) Tj ET '
SECRET = b'BT /F1 12 Tf 48 750 Td (Amount 123.45) Tj ET '


def masked_pdf(path, *, form=False, mode='Luminosity', reset=False, blend=False):
    fixture(path, content=HEADING)
    writer = PdfWriter()
    page = writer.add_page(PdfReader(path).pages[0])
    mask = DecodedStreamObject()
    mask.set_data(b'0 g 0 0 612 792 re f' if mode == 'Luminosity' else b'')
    mask.update({NameObject('/Type'): NameObject('/XObject'),
                 NameObject('/Subtype'): NameObject('/Form'),
                 NameObject('/BBox'): RectangleObject([0,0,612,792]),
                 NameObject('/Resources'): DictionaryObject(),
                 NameObject('/Group'): DictionaryObject({
                     NameObject('/S'): NameObject('/Transparency'),
                     NameObject('/CS'): NameObject('/DeviceGray')})})
    gs = DictionaryObject({NameObject('/SMask'): DictionaryObject({
        NameObject('/S'): NameObject('/'+mode), NameObject('/G'): writer._add_object(mask)})})
    if blend:
        gs = DictionaryObject({NameObject('/BM'): NameObject('/Screen')})
    page['/Resources'][NameObject('/ExtGState')] = DictionaryObject({
        NameObject('/GS'): writer._add_object(gs),
        NameObject('/Reset'): writer._add_object(DictionaryObject({NameObject('/SMask'): NameObject('/None')}))})
    text = SECRET
    if form:
        child = DecodedStreamObject()
        child.set_data(SECRET)
        child.update({NameObject('/Type'): NameObject('/XObject'),
                      NameObject('/Subtype'): NameObject('/Form'),
                      NameObject('/BBox'): RectangleObject([0,0,612,792]),
                      NameObject('/Resources'): DictionaryObject({NameObject('/Font'): page['/Resources']['/Font']})})
        page['/Resources'][NameObject('/XObject')] = DictionaryObject({NameObject('/Text'): writer._add_object(child)})
        text = b'/Text Do '
    stream = DecodedStreamObject()
    stream.set_data(HEADING + b'q /GS gs ' + (b'/Reset gs ' if reset else b'') + text + b'Q')
    page[NameObject('/Contents')] = writer._add_object(stream)
    writer.write(path)


class TextTransparencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root/'synthetic.pdf'

    def tearDown(self):
        self.temp.cleanup()

    def rendered(self):
        with pdf.PdfDocument(self.source) as doc, closing(doc[0]) as page:
            with closing(page.render(scale=2)) as bitmap:
                return bitmap.to_pil().convert('RGB').copy()

    def test_masked_text_is_visually_absent_but_requires_ocr(self):
        fixture(self.source, content=HEADING)
        visible_only = self.rendered()
        for mode in ('Luminosity', 'Alpha'):
            for form in (False, True):
                with self.subTest(mode=mode, form=form):
                    masked_pdf(self.source, mode=mode, form=form)
                    self.assertIsNone(ImageChops.difference(visible_only,self.rendered()).getbbox())
                    with pdf.PdfDocument(self.source) as doc, closing(doc[0]) as page:
                        self.assertTrue(needs_ocr(page)[0])

    def test_page_level_transparency_is_not_a_sufficient_guard(self):
        masked_pdf(self.source)
        with pdf.PdfDocument(self.source) as doc, closing(doc[0]) as page:
            self.assertFalse(pdf.raw.FPDFPage_HasTransparency(page))
            self.assertTrue(any(pdf.raw.FPDFPageObj_HasTransparency(o) for o in page.get_objects()))
            self.assertTrue(needs_ocr(page)[0])

    def test_soft_mask_reset_stays_native(self):
        masked_pdf(self.source, reset=True)
        with pdf.PdfDocument(self.source) as doc, closing(doc[0]) as page:
            self.assertFalse(needs_ocr(page)[0])
        output = self.root/'reset.docx'
        with patch('worker.OCR.recognize', side_effect=AssertionError('not masked')):
            convert(self.source, output)
        self.assertIn('Amount 123.45', '\n'.join(p.text for p in Document(output).paragraphs))

    def test_nondefault_text_blend_routes_to_ocr(self):
        for form in (False, True):
            masked_pdf(self.source, form=form, blend=True)
            with pdf.PdfDocument(self.source) as doc, closing(doc[0]) as page:
                self.assertTrue(needs_ocr(page)[0])

    def test_no_output_without_ocr(self):
        for form in (False, True):
            masked_pdf(self.source, form=form)
            output = self.root/'result.docx'
            with patch.dict('os.environ', {}, clear=True):
                with self.assertRaisesRegex(Rejected, 'OCR worker is not configured'):
                    convert(self.source, output)
            self.assertFalse(output.exists())

    def test_recognized_result_never_uses_hidden_native_text(self):
        masked_pdf(self.source)
        output = self.root/'result.docx'
        recognized = [dict(kind='paragraph', bbox=[48,80,140,100], text='Visible heading', source='test', size=12)]
        with patch('worker.OCR.recognize', return_value=recognized) as recognize:
            result = convert(self.source, output)
        recognize.assert_called_once()
        self.assertEqual([p.text for p in Document(output).paragraphs], ['Visible heading'])
        self.assertTrue(any('recognized with OCR' in w for w in result['warnings']))


if __name__ == '__main__':
    unittest.main()
