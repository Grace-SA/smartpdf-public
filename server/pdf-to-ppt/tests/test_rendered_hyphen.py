"""Rendered line-end hyphens keep their real geometry and strict text match."""
from contextlib import closing
import pypdfium2 as pdfium
import pytest
from pptx import Presentation
from reportlab.pdfgen import canvas
from smartppt.layout import add_text
from smartppt.ocr_fit import observed_boxes


def sample(tmp_path):
    path=tmp_path/'wrapped.pdf'
    c=canvas.Canvas(str(path),pagesize=(300,400));c.setFont('Helvetica',12)
    c.drawString(30,350,'wrap-');c.drawString(30,330,'ped');c.save()
    return path


def slide(text='wrap-'):
    p=Presentation();s=p.slides.add_slide(p.slide_layouts[6])
    add_text(s,text,30,40,60,20,12)
    return s


def test_real_pdfium_line_end_marker_retains_original_box(tmp_path):
    with pdfium.PdfDocument(sample(tmp_path)) as doc,closing(doc[0]) as page,closing(page.get_textpage()) as tp:
        markers=[i for i in range(tp.count_chars()) if pdfium.raw.FPDFText_GetUnicode(tp,i)==2]
        assert len(markers)==1 and pdfium.raw.FPDFText_IsHyphen(tp,markers[0])==1
        boxes=[tp.get_charbox(i) for i in range(markers[0]+1)]
        expected=(min(b[0] for b in boxes),400-max(b[3] for b in boxes),max(b[2] for b in boxes),400-min(b[1] for b in boxes))
        assert observed_boxes(page,slide(),[{'shape':0,'bbox':expected}])=={0:expected}
        assert observed_boxes(page,slide('wrxp-'),[{'shape':0,'bbox':expected}])=={}
        assert observed_boxes(page,slide(),[{'shape':0,'bbox':[x+100 for x in expected]}])=={}


@pytest.mark.parametrize('flag',[0,-1])
def test_unconfirmed_control_code_is_not_treated_as_hyphen(tmp_path,monkeypatch,flag):
    monkeypatch.setattr(pdfium.raw,'FPDFText_IsHyphen',lambda tp,i:flag)
    with pdfium.PdfDocument(sample(tmp_path)) as doc,closing(doc[0]) as page:
        assert observed_boxes(page,slide(),[{'shape':0,'bbox':[30,40,60,50]}])=={}


def test_missing_hyphen_is_not_invented(tmp_path):
    path=tmp_path/'missing.pdf';c=canvas.Canvas(str(path),pagesize=(300,400));c.setFont('Helvetica',12)
    c.drawString(30,350,'wrap');c.drawString(30,330,'ped');c.save()
    with pdfium.PdfDocument(path) as doc,closing(doc[0]) as page:
        assert observed_boxes(page,slide(),[{'shape':0,'bbox':[30,40,60,50]}])=={}
