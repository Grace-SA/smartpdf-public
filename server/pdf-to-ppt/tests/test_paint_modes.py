from contextlib import closing
import numpy as np
import pypdfium2 as pdfium
import pytest
from reportlab.pdfgen import canvas
from pptx import Presentation
from pptx.util import Pt
from smartppt.layout import extract_native,native_slide,page_background
from smartppt.quality import shape_text


@pytest.mark.parametrize('mode,alpha',[(0,0),(0,.25),(1,1),(2,1),(4,1),(5,1),(6,1),(7,1)])
def test_unsupported_paint_preserves_source_pixels(tmp_path,mode,alpha):
    path=tmp_path/'paint.pdf';c=canvas.Canvas(str(path),pagesize=(400,200))
    c.setFillColorRGB(1,0,0);c.setStrokeColorRGB(0,0,1);c.setFillAlpha(alpha)
    text=c.beginText(30,100);text.setFont('Helvetica',20);text.setTextRenderMode(mode)
    text.textOut('AMOUNT 123.45');c.drawText(text)
    if mode>=4:
        c.setFillColorRGB(0,1,0);c.rect(0,0,400,200,fill=1,stroke=0)
    c.save()
    with pdfium.PdfDocument(path) as doc,closing(doc[0]) as page:
        before=np.asarray(page_background(page,[]))
        runs,remove,warnings=extract_native(page)
        assert runs==[] and remove==[] and warnings
        assert np.array_equal(before,np.asarray(page_background(page,remove)))
        prs=Presentation();prs.slide_width=Pt(400);prs.slide_height=Pt(200)
        report=native_slide(prs,page)
        assert report['editable_runs']==0 and shape_text(prs.slides[0].shapes)==[]


def test_opaque_fill_remains_editable(tmp_path):
    path=tmp_path/'opaque.pdf';c=canvas.Canvas(str(path),pagesize=(400,200))
    c.drawString(30,100,'AMOUNT 123.45');c.save()
    with pdfium.PdfDocument(path) as doc,closing(doc[0]) as page:
        runs,remove,warnings=extract_native(page)
        assert ''.join(r['text'] for r in runs)=='AMOUNT 123.45'
        assert len(remove)==1 and not warnings
