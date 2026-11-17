"""Cropped source pages must use the same origin as the visible page raster."""
from contextlib import closing

import pypdfium2 as pdfium
import pytest
from pptx import Presentation
from pptx.util import Pt
from pypdf import PdfWriter
from pypdf.generic import RectangleObject
from reportlab.pdfgen import canvas
from PIL import ImageChops

from smartppt.layout import extract_native, native_slide


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('box_kind', ['cropbox', 'mediabox'])
def test_cropped_text_aligns_with_visible_page(tmp_path, rotation, box_kind):
    raw = tmp_path/'raw.pdf'
    source = tmp_path/'cropped.pdf'
    c = canvas.Canvas(str(raw), pagesize=(600, 800))
    # Cancel the page rotation so the resulting visible text is horizontal.
    # A counterclockwise text transform becomes horizontal after clockwise page rotation.
    c.translate(160, 600)
    c.rotate(rotation)
    c.setFont('Helvetica', 12)
    c.drawString(0, 0, 'Amount 42')
    c.save()
    writer = PdfWriter(clone_from=raw)
    setattr(writer.pages[0], box_kind, RectangleObject((50, 500, 350, 750)))
    writer.pages[0].rotate(rotation)
    writer.write(source)

    with pdfium.PdfDocument(source) as doc, closing(doc[0]) as page:
        width, height = page.get_size()
        runs, _, warnings = extract_native(page)
        assert ''.join(run['text'] for run in runs) == 'Amount 42'
        assert not warnings
        left, bottom, right, top = runs[0]['box']
        assert 0 < left < right < width
        assert 0 < bottom < top < height
        assert right-left > top-bottom
        # Independent PDFium device transform provides raster-space expected bounds.
        from ctypes import c_int, byref
        raw_points = []
        with closing(page.get_textpage()) as textpage:
            for index in range(textpage.count_chars()):
                if textpage.get_text_range(index, 1).strip():
                    l, b, r, t = textpage.get_charbox(index)
                    for x, y in [(l,b), (l,t), (r,b), (r,t)]:
                        dx, dy = c_int(), c_int()
                        assert pdfium.raw.FPDF_PageToDevice(page, 0, 0, round(width), round(height),
                                                          0, x, y, byref(dx), byref(dy))
                        raw_points.append((dx.value, dy.value))
        expected = (min(x for x,y in raw_points), height-max(y for x,y in raw_points),
                    max(x for x,y in raw_points), height-min(y for x,y in raw_points))
        assert runs[0]['box'] == pytest.approx(expected, abs=1)
        prs = Presentation()
        prs.slide_width, prs.slide_height = Pt(width), Pt(height)
        report = native_slide(prs, page)
        shape = prs.slides[0].shapes[-1]
        assert report['editable_runs'] == 1
        assert shape.text == 'Amount 42'
        assert 0 < shape.left < prs.slide_width
        assert 0 < shape.top < prs.slide_height


@pytest.mark.parametrize('x,y', [(40,600), (80,498), (20,200)])
def test_clipped_text_object_stays_in_source_raster(tmp_path, x, y):
    raw = tmp_path/'raw.pdf'
    source = tmp_path/'cropped.pdf'
    c = canvas.Canvas(str(raw), pagesize=(600,800))
    c.setFont('Helvetica',12)
    c.drawString(x,y,'Partly visible or outside 42')
    c.save()
    writer = PdfWriter(clone_from=raw)
    writer.pages[0].cropbox = RectangleObject((50,500,350,750))
    writer.write(source)
    with pdfium.PdfDocument(source) as doc, closing(doc[0]) as page:
        runs, remove, warnings = extract_native(page)
        assert runs == [] and remove == []
        assert 'clipped_text_kept_as_graphic' in warnings
        width,height = page.get_size()
        with closing(page.render(scale=2.5)) as bitmap:
            original = bitmap.to_pil().convert('RGB').copy()
        prs = Presentation()
        prs.slide_width,prs.slide_height = Pt(width),Pt(height)
        native_slide(prs,page)
        assert len(prs.slides[0].shapes) == 1
        from io import BytesIO
        from PIL import Image
        background = Image.open(BytesIO(prs.slides[0].shapes[0].image.blob)).convert('RGB')
        assert ImageChops.difference(original,background).getbbox() is None
