"""Synthetic gradients must not expose text covered in the visible PDF."""
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from PIL import ImageChops
import pypdfium2 as pdf
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (NameObject, DictionaryObject, DecodedStreamObject,
                           RectangleObject, ArrayObject, NumberObject, FloatObject,
                           BooleanObject)
from model import Rejected
from worker import needs_ocr, convert
from test_worker import fixture
from test_text_transparency import SECRET, HEADING


def shading_pdf(path, *, radial=False, before=False, x=96, clip=True, form=False,
                dx=0, blend=False):
    fixture(path, content=SECRET+HEADING)
    writer = PdfWriter()
    page = writer.add_page(PdfReader(path).pages[0])
    function = DictionaryObject({NameObject('/FunctionType'): NumberObject(2),
        NameObject('/Domain'): ArrayObject([NumberObject(0),NumberObject(1)]),
        NameObject('/C0'): ArrayObject([FloatObject(1)]*3),
        NameObject('/C1'): ArrayObject([FloatObject(.9)]*3), NameObject('/N'): NumberObject(1)})
    coords = (x+4,755,0,x+4,755,15) if radial else (x,745,x+8,765)
    shading = DictionaryObject({NameObject('/ShadingType'): NumberObject(3 if radial else 2),
        NameObject('/ColorSpace'): NameObject('/DeviceRGB'),
        NameObject('/Coords'): ArrayObject([FloatObject(v) for v in coords]),
        NameObject('/BBox'): RectangleObject([x,745,x+8,765]),
        NameObject('/Function'): writer._add_object(function),
        NameObject('/Extend'): ArrayObject([BooleanObject(True),BooleanObject(True)])})
    resources = DictionaryObject({NameObject('/Shading'): DictionaryObject({
        NameObject('/Sh'): writer._add_object(shading)})})
    if blend:
        resources[NameObject('/ExtGState')] = DictionaryObject({
            NameObject('/GS'): writer._add_object(DictionaryObject({NameObject('/BM'):NameObject('/Screen')}))})
    commands = b'q ' + (b'/GS gs ' if blend else b'')
    commands += (f'{x} 745 8 20 re W n '.encode() if clip else b'') + b'/Sh sh Q '
    if form:
        obj = DecodedStreamObject()
        obj.set_data(commands)
        obj.update({NameObject('/Type'):NameObject('/XObject'),
                    NameObject('/Subtype'):NameObject('/Form'),
                    NameObject('/BBox'):RectangleObject([0,0,612,792]),
                    NameObject('/Resources'):resources,
                    NameObject('/Matrix'):ArrayObject([FloatObject(v) for v in (1,0,0,1,dx,0)])})
        page['/Resources'][NameObject('/XObject')] = DictionaryObject({NameObject('/Fo'):writer._add_object(obj)})
        commands = b'/Fo Do '
    else:
        page['/Resources'].update(resources)
    stream = DecodedStreamObject()
    stream.set_data(commands+SECRET+HEADING if before else SECRET+HEADING+commands)
    page[NameObject('/Contents')] = writer._add_object(stream)
    writer.write(path)


class ShadingPaintTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root/'synthetic.pdf'

    def tearDown(self):
        self.temp.cleanup()

    def routed(self):
        with pdf.PdfDocument(self.source) as doc, closing(doc[0]) as page:
            return needs_ocr(page)[0]

    def render(self):
        with pdf.PdfDocument(self.source) as doc, closing(doc[0]) as page:
            with closing(page.render(scale=2)) as bitmap:
                return bitmap.to_pil().convert('RGB').copy()

    def test_axial_and_radial_gradient_changes_pixels_and_requires_ocr(self):
        fixture(self.source,content=SECRET+HEADING)
        baseline = self.render()
        for radial in (False,True):
            shading_pdf(self.source,radial=radial)
            rendered = self.render()
            self.assertIsNotNone(ImageChops.difference(baseline,rendered).getbbox())
            # The covered digit region loses dark glyph pixels, not merely background pixels.
            region = (194,56,206,92)
            original_dark = sum(v < 80 for v in baseline.convert('L').crop(region).tobytes())
            covered_dark = sum(v < 80 for v in rendered.convert('L').crop(region).tobytes())
            self.assertGreater(original_dark,0)
            self.assertEqual(covered_dark,0)
            self.assertTrue(self.routed())

    def test_background_gradient_does_not_cover_later_text(self):
        shading_pdf(self.source,before=True)
        self.assertFalse(self.routed())

    def test_disjoint_explicit_clip_remains_native(self):
        shading_pdf(self.source,x=300)
        self.assertFalse(self.routed())

    def test_bbox_without_explicit_clip_can_conservatively_require_ocr(self):
        # PDFium exposes page-wide bounds here despite the shading dictionary BBox.
        shading_pdf(self.source,x=300,clip=True)
        visible = self.render()
        shading_pdf(self.source,x=300,clip=False)
        self.assertIsNone(ImageChops.difference(visible,self.render()).getbbox())
        self.assertTrue(self.routed())

    def test_form_transform_and_disjoint_counterexample(self):
        for dx,expected in ((0,True),(200,False)):
            shading_pdf(self.source,form=True,dx=dx)
            self.assertEqual(self.routed(),expected)

    def test_screen_blending_still_requires_ocr(self):
        for form in (False,True):
            shading_pdf(self.source,blend=True,form=form)
            self.assertTrue(self.routed())

    def test_no_native_output_without_ocr(self):
        shading_pdf(self.source)
        output = self.root/'result.docx'
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaisesRegex(Rejected,'OCR worker is not configured'):
                convert(self.source,output)
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
