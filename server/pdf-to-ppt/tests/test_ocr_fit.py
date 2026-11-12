from copy import deepcopy
import pytest
from pptx import Presentation
from pptx.util import Pt
from smartppt.layout import add_text
from smartppt.ocr_fit import fit_shape,local_box,observed_boxes


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_quarter_turn_font_fit_preserves_content_and_rotation(angle):
    prs=Presentation();slide=prs.slides.add_slide(prs.slide_layouts[6])
    shape=add_text(slide,'Total −123.45',40,50,140,30,20,'Arial',italic=True);shape.rotation=angle
    desired=[44,54,160,71] if angle in (0,180) else [94,20,111,136]
    observed=[x+1 for x in desired]
    assert fit_shape(shape,desired,observed)
    assert shape.text=='Total −123.45' and shape.rotation==angle
    assert shape.text_frame.paragraphs[0].runs[0].font.italic


def test_skew_and_implausible_font_scale_are_left_unchanged():
    prs=Presentation();slide=prs.slides.add_slide(prs.slide_layouts[6]);shape=add_text(slide,'123.45',20,20,80,20,12)
    shape.rotation=3;before=shape._element.xml
    assert not fit_shape(shape,[20,20,90,30],[20,20,90,30]) and shape._element.xml==before
    shape.rotation=0;before=shape._element.xml
    assert not fit_shape(shape,[20,20,90,30],[20,20,90,25]) and shape._element.xml==before


def test_inverse_rectangle_geometry():
    assert local_box((10,20,40,30),0,0,90)==pytest.approx((20,-40,30,-10))


def test_duplicate_text_is_assigned_near_its_expected_region(tmp_path):
    from reportlab.pdfgen import canvas
    from contextlib import closing
    import pypdfium2 as pdfium
    path=tmp_path/'same.pdf';c=canvas.Canvas(str(path),pagesize=(300,400));c.setFont('Helvetica',12)
    c.drawString(30,350,'123.45');c.drawString(30,100,'123.45');c.save()
    prs=Presentation();slide=prs.slides.add_slide(prs.slide_layouts[6])
    add_text(slide,'123.45',30,300,60,20,12);add_text(slide,'123.45',30,50,60,20,12)
    targets=[{'shape':0,'bbox':[30,290,70,301]},{'shape':1,'bbox':[30,40,70,51]}]
    with pdfium.PdfDocument(path) as doc,closing(doc[0]) as page:result=observed_boxes(page,slide,targets)
    assert set(result)=={0,1} and result[0][1]>280 and result[1][1]<60


def test_scan_fit_render_is_bounded_for_large_page():
    from smartppt.ocr_fit import raster_bounds
    from PIL import Image
    calls=[]
    class Bitmap:
        def close(self):pass
        def to_pil(self):return Image.new('RGB',(2400,2400),'white')
    class Page:
        def get_size(self):return (14400,14400)
        def render(self,scale):calls.append(scale);return Bitmap()
    assert raster_bounds(Page(),None,[],{})=={}
    assert calls==[1/6]


@pytest.mark.parametrize('page_size',[600,4000])
def test_skew_measurement_center_is_independent_of_raster_scale(page_size):
    import math
    from PIL import Image,ImageDraw
    from smartppt.ocr_fit import raster_bounds
    prs=Presentation();slide=prs.slides.add_slide(prs.slide_layouts[6])
    shape=add_text(slide,'Total 123.45',100,150,200,40,12);shape.rotation=3
    cx,cy=200,170;c,s=math.cos(math.radians(3)),math.sin(math.radians(3))
    rectangle=[(104,159),(245,159),(245,178),(104,178)]
    quad=[(cx+(x-cx)*c-(y-cy)*s,cy+(x-cx)*s+(y-cy)*c) for x,y in rectangle]
    scale=min(2,2400/page_size)
    image=Image.new('RGB',(round(page_size*scale),round(page_size*scale)),'white')
    ImageDraw.Draw(image).polygon([(x*scale,y*scale) for x,y in quad],fill='black')
    class Bitmap:
        def close(self):pass
        def to_pil(self):return image
    class Page:
        def get_size(self):return (page_size,page_size)
        def render(self,scale):return Bitmap()
    observed=[min(x for x,y in quad),min(y for x,y in quad),max(x for x,y in quad),max(y for x,y in quad)]
    desired,actual=raster_bounds(Page(),slide,[{'shape':0,'quad':quad}],{0:observed})[0]
    assert desired==pytest.approx((104,159,245,178))
    assert actual==pytest.approx(desired,abs=2/scale+1e-6)


@pytest.mark.skipif(not __import__('os').getenv('SMARTPPT_TEST_RENDERER'),reason='real Office renderer required')
def test_real_font_fit_and_rejected_page_restore(tmp_path,settings,monkeypatch):
    import os
    from contextlib import closing
    import pypdfium2 as pdfium
    from reportlab.pdfgen import canvas
    import smartppt.ocr_fit as fitter
    source=tmp_path/'scan-reference.pdf';c=canvas.Canvas(str(source),pagesize=(300,400))
    for _ in range(2):c.setFont('Helvetica',12);c.drawString(40,330,'Total 123.45');c.showPage()
    c.save();target=tmp_path/'result.pptx';prs=Presentation();prs.slide_width=Pt(300);prs.slide_height=Pt(400)
    for _ in range(2):add_text(prs.slides.add_slide(prs.slide_layouts[6]),'Total 123.45',42,56,150,22,12)
    prs.save(target);original=Presentation(target).slides[1].shapes[0]._element.xml
    with pdfium.PdfDocument(source) as doc,closing(doc[0]) as page,closing(page.get_textpage()) as tp:
        boxes=[tp.get_charbox(i) for i in range(tp.count_chars())]
        box=[min(b[0] for b in boxes),400-max(b[3] for b in boxes),max(b[2] for b in boxes),400-min(b[1] for b in boxes)]
    l,t,r,b=box;report=[{'page':i,'route':'paddle-ocr','ink_targets':[{'shape':0,'bbox':box,'quad':[(l,t),(r,t),(r,b),(l,b)]}]} for i in [1,2]]
    calls=[]
    def accept(a,b):calls.append(1);return len(calls)==1
    monkeypatch.setattr(fitter,'accept_candidate',accept);settings.renderer_path=os.environ['SMARTPPT_TEST_RENDERER']
    fitter.fit_ocr_pages(source,target,report,settings)
    assert report[0]['font_fit']['accepted'] and not report[1]['font_fit']['accepted']
    output=Presentation(target)
    assert output.slides[1].shapes[0]._element.xml==original
    assert all(s.shapes[0].text=='Total 123.45' for s in output.slides)
    assert not list(tmp_path.glob('smartppt-scan-fit-*'))
