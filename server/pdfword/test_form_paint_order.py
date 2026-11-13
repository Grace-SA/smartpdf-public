"""Public synthetic nested Form painting and simple stroked occluders."""
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from PIL import ImageChops
import pypdfium2 as pdf
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (NameObject, DictionaryObject, DecodedStreamObject,
                           RectangleObject, ArrayObject, FloatObject)
from model import Rejected
from worker import needs_ocr, convert
from test_worker import fixture

TEXT = b'BT /F1 12 Tf 48 750 Td (Amount 123.45) Tj ET '
COVER = b'q 1 1 1 rg 100 748 5 15 re f Q '


def form_pdf(path, *, inside, outside, before=False, matrices=()):
    fixture(path, content=outside)
    writer = PdfWriter()
    page = writer.add_page(PdfReader(path).pages[0])
    resources = DictionaryObject({NameObject('/Font'): page['/Resources']['/Font']})
    content = inside
    for matrix in matrices or [(1, 0, 0, 1, 0, 0)]:
        form = DecodedStreamObject()
        form.set_data(content)
        form.update({NameObject('/Type'): NameObject('/XObject'),
                     NameObject('/Subtype'): NameObject('/Form'),
                     NameObject('/BBox'): RectangleObject([-2000, -2000, 2000, 2000]),
                     NameObject('/Matrix'): ArrayObject([FloatObject(v) for v in matrix]),
                     NameObject('/Resources'): resources})
        resources = DictionaryObject({NameObject('/XObject'): DictionaryObject(
            {NameObject('/Fo'): writer._add_object(form)})})
        content = b'/Fo Do '
    page['/Resources'][NameObject('/XObject')] = resources['/XObject']
    stream = DecodedStreamObject()
    stream.set_data(content + outside if before else outside + content)
    page[NameObject('/Contents')] = writer._add_object(stream)
    writer.write(path)


class FormPaintTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'synthetic.pdf'

    def tearDown(self):
        self.temp.cleanup()

    def routed(self):
        with pdf.PdfDocument(self.source) as doc, closing(doc[0]) as page:
            return needs_ocr(page)[0]

    def test_graphic_form_after_text_requires_ocr(self):
        form_pdf(self.source, inside=COVER, outside=TEXT)
        self.assertTrue(self.routed())

    def test_nested_scale_translation_composition(self):
        # Local rectangle transforms to page [100, 748, 105, 763].
        local = b'q 1 1 1 rg 0 0 2.5 7.5 re f Q '
        form_pdf(self.source, inside=local, outside=TEXT,
                 matrices=[(2,0,0,2,0,0), (1,0,0,1,100,748)])
        self.assertTrue(self.routed())
        # Reverse the transformations: [200,1496,...], away from the text.
        form_pdf(self.source, inside=local, outside=TEXT,
                 matrices=[(1,0,0,1,100,748), (2,0,0,2,0,0)])
        self.assertFalse(self.routed())

    def test_transformed_cover_matches_page_space_render(self):
        images = []
        for nested in (False, True):
            if nested:
                form_pdf(self.source, inside=b'q 1 1 1 rg 0 0 2.5 7.5 re f Q ',
                         outside=TEXT, matrices=[(2,0,0,2,0,0), (1,0,0,1,100,748)])
            else:
                fixture(self.source, content=TEXT+COVER)
            with pdf.PdfDocument(self.source) as doc, closing(doc[0]) as page:
                with closing(page.render(scale=2)) as bitmap:
                    images.append(bitmap.to_pil().convert('RGB').copy())
        self.assertIsNone(ImageChops.difference(*images).getbbox())

    def test_nested_text_before_top_level_graphic(self):
        form_pdf(self.source, inside=TEXT, outside=COVER, before=True)
        self.assertTrue(self.routed())

    def test_internal_form_paint_order(self):
        for content, expected in ((TEXT+COVER, True), (COVER+TEXT, False)):
            form_pdf(self.source, inside=content, outside=b'')
            self.assertEqual(self.routed(), expected)

    def test_disjoint_translated_form_stays_native(self):
        form_pdf(self.source, inside=COVER, outside=TEXT,
                 matrices=[(1,0,0,1,200,0)])
        self.assertFalse(self.routed())

    def test_transformed_text_uses_page_space_safety_checks(self):
        form_pdf(self.source, inside=TEXT, outside=b'', matrices=[(1,0,0,1,-100,0)])
        self.assertTrue(self.routed())
        form_pdf(self.source, inside=TEXT, outside=b'', matrices=[(0,1,-1,0,800,0)])
        self.assertTrue(self.routed())
        form_pdf(self.source, inside=b'BT /F1 12 Tf -100 750 Td (Visible) Tj ET ',
                 outside=b'', matrices=[(1,0,0,1,150,0)])
        self.assertFalse(self.routed())

    def test_differently_transformed_siblings_reset_ancestor_stack(self):
        for dx, expected in ((0, True), (300, False)):
            form_pdf(self.source, inside=COVER, outside=TEXT,
                     matrices=[(2,0,0,2,0,0), (1,0,0,1,300,0)])
            writer = PdfWriter()
            page = writer.add_page(PdfReader(self.source).pages[0])
            form = DecodedStreamObject()
            form.set_data(COVER)
            form.update({NameObject('/Type'): NameObject('/XObject'),
                         NameObject('/Subtype'): NameObject('/Form'),
                         NameObject('/BBox'): RectangleObject([0,0,612,792]),
                         NameObject('/Matrix'): ArrayObject([FloatObject(v) for v in (1,0,0,1,dx,0)]),
                         NameObject('/Resources'): DictionaryObject()})
            page['/Resources']['/XObject'][NameObject('/Second')] = writer._add_object(form)
            stream = DecodedStreamObject()
            stream.set_data(page.get_contents().get_data() + b' /Second Do ')
            page[NameObject('/Contents')] = writer._add_object(stream)
            writer.write(self.source)
            self.assertEqual(self.routed(), expected)

    def test_recursion_boundary_requires_ocr(self):
        form_pdf(self.source, inside=COVER, outside=TEXT,
                 matrices=[(1,0,0,1,0,0)]*9)
        self.assertTrue(self.routed())

    def test_stroked_line_cover_and_counterexamples(self):
        stroke = b'q 1 1 1 RG 8 w 100 745 m 100 765 l S Q '
        for content, expected in ((TEXT+stroke, True), (stroke+TEXT, False),
                                  (TEXT+b'q 8 w 300 745 m 300 765 l S Q', False)):
            fixture(self.source, content=content)
            self.assertEqual(self.routed(), expected)

    def test_form_occlusion_no_native_output_without_ocr(self):
        form_pdf(self.source, inside=COVER, outside=TEXT)
        output = self.root / 'result.docx'
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaisesRegex(Rejected, 'OCR worker is not configured'):
                convert(self.source, output)
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
