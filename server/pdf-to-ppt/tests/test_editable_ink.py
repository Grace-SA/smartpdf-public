from contextlib import closing
import ctypes,math
import numpy as np
import pypdfium2 as pdfium
from PIL import Image,ImageDraw
from pptx import Presentation
from pptx.util import Pt
from reportlab.pdfgen import canvas
import pytest
from smartppt import ocr_fit
from smartppt.layout import add_text


def source(path,background=None):
    c=canvas.Canvas(str(path),pagesize=(300,140))
    if background is not None:c.drawImage(str(background),0,0,300,140)
    c.setFont('Helvetica',20);c.drawString(30,70,'Editable 123');c.save()


def raster(page):
    with closing(page.render(scale=2)) as b:return b.to_pil().convert('RGB').copy()


def setup(tmp_path):
    plain=tmp_path/'plain.pdf';source(plain)
    with pdfium.PdfDocument(plain) as doc,closing(doc[0]) as page,closing(page.get_textpage()) as tp:
        boxes=[tp.get_charbox(i) for i in range(tp.count_chars()) if tp.get_text_range(i,1).strip()]
        observed=(min(x[0] for x in boxes),140-max(x[3] for x in boxes),max(x[2] for x in boxes),140-min(x[1] for x in boxes))
        a=np.asarray(raster(page));ys,xs=np.where(a.min(axis=2)<225);ink=(float(xs.min())/2,float(ys.min())/2,float(xs.max()+1)/2,float(ys.max()+1)/2)
    background=Image.new('RGB',(600,280),'white');d=ImageDraw.Draw(background);y=math.floor(observed[1]*2)-3
    d.rectangle((math.floor(observed[0]*2)-4,y,math.ceil(observed[2]*2)+4,y+1),fill='black')
    png=tmp_path/'background.png';background.save(png);path=tmp_path/'with-neighbor.pdf';source(path,png)
    prs=Presentation();prs.slide_width=Pt(300);prs.slide_height=Pt(140);slide=prs.slides.add_slide(prs.slide_layouts[6]);l,t,r,b=ink
    add_text(slide,'Editable 123',l,t,r-l+20,b-t+20,20,'Arial',False,(0,0,0));target={'shape':0,'bbox':ink,'quad':[(l,t),(r,t),(r,b),(l,b)]}
    return path,slide,[target]


def test_raster_neighbor_does_not_change_measured_editable_ink(tmp_path,monkeypatch):
    path,slide,targets=setup(tmp_path)
    with pdfium.PdfDocument(path) as doc,closing(doc[0]) as page:
        original=raster(page);observed=ocr_fit.observed_boxes(page,slide,targets)
        with monkeypatch.context() as m:
            m.setattr(ocr_fit,'editable_ink_image',lambda *_:None)
            assert ocr_fit.raster_bounds(page,slide,targets,observed)=={}
        actual=ocr_fit.raster_bounds(page,slide,targets,observed)
        assert max(abs(a-b) for a,b in zip(*actual[0]))<=.5
        assert raster(page).tobytes()==original.tobytes()


def test_fallback_cannot_authorize_unmatched_text(tmp_path):
    path,slide,targets=setup(tmp_path);slide.shapes[0].text='Different 999'
    slide.shapes[0].text_frame.paragraphs[0].runs[0].font.size=Pt(20)
    with pdfium.PdfDocument(path) as doc,closing(doc[0]) as page:
        observed=ocr_fit.observed_boxes(page,slide,targets);assert not observed
        assert ocr_fit.raster_bounds(page,slide,targets,observed)=={}


def test_no_text_never_produces_editable_ink(tmp_path):
    image=tmp_path/'raster.png';Image.new('RGB',(300,140),'black').save(image);path=tmp_path/'image.pdf'
    c=canvas.Canvas(str(path),pagesize=(300,140));c.drawImage(str(image),0,0,300,140);c.save()
    with pdfium.PdfDocument(path) as doc,closing(doc[0]) as page:
        assert ocr_fit.editable_ink_image(page,raster(page),2) is None


def test_originally_inactive_objects_remain_inactive(tmp_path):
    path,_,_=setup(tmp_path)
    with pdfium.PdfDocument(path) as doc,closing(doc[0]) as page:
        obj=next(page.get_objects(filter=[pdfium.raw.FPDF_PAGEOBJ_TEXT]));assert pdfium.raw.FPDFPageObj_SetIsActive(obj,False)
        before=raster(page);assert ocr_fit.editable_ink_image(page,before,2) is None
        active=ctypes.c_int();assert pdfium.raw.FPDFPageObj_GetIsActive(obj,ctypes.byref(active));assert not active.value
        assert raster(page).tobytes()==before.tobytes()


def test_failed_background_render_restores_all_text(tmp_path,monkeypatch):
    path,_,_=setup(tmp_path)
    with pdfium.PdfDocument(path) as doc,closing(doc[0]) as page:
        before=raster(page)
        with monkeypatch.context() as m:
            def fail(*a,**kw):raise RuntimeError('synthetic rendering failure')
            m.setattr(page,'render',fail)
            assert ocr_fit.editable_ink_image(page,before,2) is None
        assert raster(page).tobytes()==before.tobytes()


def test_existing_two_point_threshold_is_not_relaxed(tmp_path):
    path,slide,targets=setup(tmp_path)
    # Shift only the independently supplied desired source location.
    targets[0]['quad']=[(x+3,y) for x,y in targets[0]['quad']]
    with pdfium.PdfDocument(path) as doc,closing(doc[0]) as page:
        observed=ocr_fit.observed_boxes(page,slide,targets);measured=ocr_fit.raster_bounds(page,slide,targets,observed)
        assert max(abs(a-b) for a,b in zip(*measured[0]))>2


@pytest.mark.parametrize('failure',['query','disable','restore'])
def test_visibility_api_failures_preserve_pixels_and_fail_closed(tmp_path,monkeypatch,failure):
    from smartppt.config import ConversionError
    path,_,_=setup(tmp_path)
    with pdfium.PdfDocument(path) as doc,closing(doc[0]) as page:
        original=raster(page);setter=pdfium.raw.FPDFPageObj_SetIsActive
        with monkeypatch.context() as m:
            if failure=='query':m.setattr(pdfium.raw,'FPDFPageObj_GetIsActive',lambda *_:False)
            else:
                def set_active(obj,active):
                    result=setter(obj,active)
                    # Simulate an API that changed state but reports failure.
                    return False if (active and failure=='restore') or (not active and failure=='disable') else result
                m.setattr(pdfium.raw,'FPDFPageObj_SetIsActive',set_active)
            if failure=='restore':
                with pytest.raises(ConversionError,match='ocr_geometry_measurement_failed'):
                    ocr_fit.editable_ink_image(page,original,2)
            else:assert ocr_fit.editable_ink_image(page,original,2) is None
        assert raster(page).tobytes()==original.tobytes()


def test_nested_form_text_is_measured_without_changing_its_transform(tmp_path):
    path=tmp_path/'form.pdf';c=canvas.Canvas(str(path),pagesize=(300,140));c.beginForm('text')
    c.setFont('Helvetica',20);c.drawString(0,0,'Nested 789');c.endForm();c.saveState();c.translate(30,60);c.scale(1.2,.9);c.doForm('text');c.restoreState();c.save()
    with pdfium.PdfDocument(path) as doc,closing(doc[0]) as page:
        before=raster(page);difference=ocr_fit.editable_ink_image(page,before,2)
        assert difference is not None and np.array_equal(np.asarray(difference),np.asarray(before))
        assert raster(page).tobytes()==before.tobytes()
