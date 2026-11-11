from contextlib import closing
import hashlib
from io import BytesIO
import numpy as np
import pytest
import pypdfium2 as pdfium
from PIL import Image,ImageDraw,ImageFont
from pptx import Presentation
from pptx.util import Pt
from reportlab.pdfgen import canvas
from smartppt.layout import extract_native,page_background,font_family,convert_native
from smartppt.regional import objects_for_page,acceptable_region,pixel_score,region_box
from smartppt.deskew import rectified_line
from smartppt.assisted import ocr_slide
from smartppt.content_gate import enforce_content_safety
from smartppt.pdf import inspect_pdf


def test_unresolved_character_keeps_entire_object(tmp_path,monkeypatch):
    source=tmp_path/'broken.pdf';c=canvas.Canvas(str(source));c.drawString(50,700,'Exact 123.45');c.save()
    original=pdfium.raw.FPDFText_GetFontSize
    monkeypatch.setattr(pdfium.raw,'FPDFText_GetFontSize',lambda tp,i:float('nan') if i==3 else original(tp,i))
    with pdfium.PdfDocument(source) as doc,closing(doc[0]) as page:
        runs,objects,warnings=extract_native(page)
        assert not runs and not objects
        assert 'incomplete_text_object_kept_as_graphic' in warnings


def test_failed_deactivation_restores_objects(pdf_file,monkeypatch):
    calls=[]
    def active(obj,value):calls.append((obj,value));return not (obj=='bad' and not value)
    monkeypatch.setattr(pdfium.raw,'FPDFPageObj_SetIsActive',active)
    with pdfium.PdfDocument(pdf_file) as doc:
        with pytest.raises(RuntimeError):page_background(doc[0],['good','bad'])
    assert calls==[('good',False),('bad',False),('good',True)]


def test_font_flags_resolve_obfuscated_names():
    assert font_family('ABC123','Amount 123',34)[0]=='Times New Roman'
    assert font_family('ABC123','Amount 123',33)[0]=='Courier New'
    assert font_family('ABC123','中文',34)[0]=='Noto Sans SC'


def test_stroked_or_clipping_text_is_not_candidate(tmp_path):
    path=tmp_path/'stroke.pdf';c=canvas.Canvas(str(path))
    for mode in [1,2,4,5,6,7]:
        t=c.beginText(40,700-mode*40);t.setTextRenderMode(mode);t.textOut('Stroke 123');c.drawText(t)
    c.save()
    with pdfium.PdfDocument(path) as doc:assert not objects_for_page(doc[0])[0]


def test_italic_descriptor_preserved(tmp_path):
    path=tmp_path/'italic.pdf';c=canvas.Canvas(str(path));c.setFont('Times-Italic',12);c.drawString(20,700,'Italic 123');c.save()
    target=tmp_path/'italic.pptx';convert_native(path,target)
    runs=[r for s in Presentation(target).slides[0].shapes if s.has_text_frame for p in s.text_frame.paragraphs for r in p.runs]
    assert runs and all(r.font.italic and r.font.name=='Times New Roman' for r in runs)


def test_pixel_gate_rejects_displacement():
    a=Image.new('RGB',(150,50),'white');b=a.copy()
    ImageDraw.Draw(a).rectangle((10,10,120,35),fill='black');ImageDraw.Draw(b).rectangle((30,10,140,35),fill='black')
    assert acceptable_region(pixel_score(a,a)) and not acceptable_region(pixel_score(a,b))
    p=Presentation();p.slide_width=Pt(100);p.slide_height=Pt(100)
    assert region_box((-1,10,50,40),(1000,1000),p) is None


@pytest.mark.parametrize('polygon',[
    [[20,20],[20,100],[0,100],[0,20]],
    [[20,20],[180,30],[160,80],[20,40]],
    [[0,0],[180,10],[178,30],[0,20]],
])
def test_unsafe_deskew_refused(polygon):
    assert rectified_line(Image.new('RGB',(200,200),'white'),polygon) is None


def test_deskew_preserves_text_rotation_and_surroundings(tmp_path):
    font=ImageFont.load_default(size=28)
    base=Image.new('RGB',(450,160),'white');ImageDraw.Draw(base).text((60,55),'Amount 123.45',font=font,fill='black')
    im=base.rotate(3,resample=Image.Resampling.BICUBIC,fillcolor='white')
    l,t,r,b=ImageDraw.Draw(base).textbbox((60,55),'Amount 123.45',font=font)
    angle=np.radians(-3);matrix=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
    center=np.array([225,80]);polygon=[((np.array([x,y])-center)@matrix.T+center).tolist() for x,y in [(l-3,t-3),(r+3,t-3),(r+3,b+3),(l-3,b+3)]]
    path=tmp_path/'scan.png';im.save(path)
    record={'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'image_size':list(im.size),'lines':[{'text':'Amount 123.45','confidence':.99,'polygon':polygon}]}
    source=tmp_path/'scan.pdf';c=canvas.Canvas(str(source),pagesize=im.size);c.drawImage(str(path),0,0,*im.size);c.save()
    p=Presentation();p.slide_width=Pt(450);p.slide_height=Pt(160);slide=p.slides.add_slide(p.slide_layouts[6])
    with pdfium.PdfDocument(source) as doc:report=ocr_slide(p,slide,doc[0],path,record,line_approvals=[True])
    assert report['deskewed_lines']==1 and report['editable_lines']==1
    text=next(s for s in slide.shapes if s.has_text_frame)
    assert text.text=='Amount 123.45' and text.rotation==pytest.approx(357,abs=.01)
    result=Image.open(BytesIO(slide.shapes[0].image.blob)).convert('RGB')
    assert np.array_equal(np.asarray(result)[:25],np.asarray(im)[:25])
    from smartppt.consensus import erase_bounds
    l,t,r,b=erase_bounds(record['lines'][0])
    outside=np.ones((im.height,im.width),dtype=bool);outside[max(0,t):min(im.height,b),max(0,l):min(im.width,r)]=False
    assert np.array_equal(np.asarray(result)[outside],np.asarray(im)[outside])
    p2=Presentation();s2=p2.slides.add_slide(p2.slide_layouts[6])
    with pdfium.PdfDocument(source) as doc:rejected=ocr_slide(p2,s2,doc[0],path,record,line_approvals=[False])
    assert rejected['editable_lines']==0


def test_missing_renderer_retains_image(pdf_file,tmp_path,settings):
    target=tmp_path/'target.pptx';pages=convert_native(pdf_file,target)
    p=Presentation(target);next(s for s in p.slides[0].shapes if s.has_text_frame).text='Wrong 999';p.save(target)
    report=enforce_content_safety(pdf_file,target,inspect_pdf(pdf_file),{'pages':[{'page':i+1,**v} for i,v in enumerate(pages)]},settings)
    assert report['source_image_pages']==[1] and report['regional_recovery_error']=='layout_renderer_not_configured'
    assert len(Presentation(target).slides[0].shapes)==1
    assert not list(tmp_path.glob('smartppt-regions-*'))


def test_a_short_bad_line_cannot_hide_in_a_large_object():
    from smartppt.regional import score_regions
    a=Image.new('RGB',(500,500),'white');b=a.copy()
    ImageDraw.Draw(a).rectangle((20,20,80,35),fill='black')
    ImageDraw.Draw(b).rectangle((20,20,80,35),fill='black')
    ImageDraw.Draw(a).rectangle((20,420,30,435),fill='black')
    p=Presentation();p.slide_width=Pt(500);p.slide_height=Pt(500)
    assert score_regions(a,b,[(10,10,100,50),(10,410,50,450)],p) is None


def test_dark_background_does_not_dilute_missing_white_text():
    from smartppt.regional import score_regions
    a=Image.new('RGB',(500,100),'black');b=a.copy()
    ImageDraw.Draw(a).rectangle((20,20,25,35),fill='white')
    p=Presentation();p.slide_width=Pt(500);p.slide_height=Pt(100)
    assert score_regions(a,b,[(0,0,500,100)],p) is None


def test_nonfinite_and_empty_region_refused():
    p=Presentation()
    for box in [(1,1,1,2),(0,0,float('nan'),5),(0,0,1,float('inf'))]:
        assert region_box(box,(800,600),p) is None


def test_source_is_rendered_directly_on_target_grid(tmp_path):
    from smartppt.regional import aligned_source
    path=tmp_path/'source.pdf';c=canvas.Canvas(str(path),pagesize=(600,800));c.drawString(30,700,'Thin text 123.45');c.save()
    with pdfium.PdfDocument(path) as doc,closing(doc[0]) as page:
        result=aligned_source(page,(1201,1601))
        assert result.size==(1201,1601)
        # Same pixel grid as a direct PDF render when dimensions divide exactly.
        with closing(page.render(scale=2)) as bitmap:
            expected=bitmap.to_pil().convert('RGB').copy()
        assert np.array_equal(np.asarray(aligned_source(page,(1200,1600))),np.asarray(expected))


def test_vertical_detection_is_not_erased_even_with_consensus(tmp_path):
    im=Image.new('RGB',(120,300),'white');ImageDraw.Draw(im).rectangle((40,40,60,250),fill='black')
    path=tmp_path/'vertical.png';im.save(path)
    record={'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'image_size':[120,300],
        'lines':[{'text':'Vertical 123','confidence':.99,'polygon':[[35,35],[65,35],[65,255],[35,255]]}]}
    source=tmp_path/'source.pdf';c=canvas.Canvas(str(source),pagesize=im.size);c.drawImage(str(path),0,0,*im.size);c.save()
    p=Presentation();slide=p.slides.add_slide(p.slide_layouts[6])
    with pdfium.PdfDocument(source) as doc:result=ocr_slide(p,slide,doc[0],path,record,line_approvals=[True])
    assert result['editable_lines']==0 and 'rotated_ocr_kept_as_image' in result['warnings']
    assert np.array_equal(np.asarray(Image.open(BytesIO(slide.shapes[0].image.blob))),np.asarray(im))


def test_whole_page_gate_compares_same_renderer_baseline():
    from smartppt.regional import acceptable_page
    baseline={'mae':.005,'foreground_mae':.18}
    assert acceptable_page(baseline,{'mae':.003,'foreground_mae':.13})
    assert not acceptable_page(baseline,{'mae':.02,'foreground_mae':.13})
    assert not acceptable_page(baseline,{'mae':.003,'foreground_mae':.25})


@pytest.mark.skipif(not __import__('os').getenv('SMARTPPT_TEST_RENDERER'),reason='optional real Office acceptance; renderer required')
def test_real_regional_recovery_and_rejected_page_restore(tmp_path,settings,monkeypatch):
    import os
    import smartppt.regional as regional
    settings.renderer_path=os.environ['SMARTPPT_TEST_RENDERER']
    source=tmp_path/'mixed.pdf';c=canvas.Canvas(str(source),pagesize=(600,800))
    for _ in range(2):
        c.setFont('Times-Italic',16);c.drawString(50,740,'Synthetic columns: 123.45');c.setFont('Helvetica',12)
        for n in range(8):
            c.drawString(50,680-n*35,f'North row {n+1}: 123.45');c.drawString(330,680-n*35,f'South row {n+1}: 678.90')
        c.saveState();c.translate(30,300);c.rotate(90);c.drawString(0,0,'Vertical label 987.65');c.restoreState()
        c.setStrokeColorRGB(0,.2,.7);c.rect(50,100,500,150);c.showPage()
    c.save();target=tmp_path/'result.pptx';p=Presentation();p.slide_width=Pt(600);p.slide_height=Pt(800)
    for _ in range(2):
        s=p.slides.add_slide(p.slide_layouts[6]);s.shapes.add_textbox(Pt(50),Pt(50),Pt(100),Pt(20)).text='Wrong 999'
    p.save(target);info=inspect_pdf(source)
    report={'pages':[{'page':i,'route':'stirling-retained'} for i in [1,2]]}
    enforce_content_safety(source,target,info,report)
    original=Presentation(target).slides[1].shapes[0].image.blob
    check=regional.acceptable_page;calls=[]
    def reject_second(a,b):calls.append(1);return len(calls)==1 and check(a,b)
    monkeypatch.setattr(regional,'acceptable_page',reject_second)
    enforce_content_safety(source,target,info,report,settings)
    assert report['partial_native_pages']==[1] and report['source_image_pages']==[2]
    output=Presentation(target)
    texts=[s.text for s in output.slides[0].shapes if s.has_text_frame]
    assert texts and all(t in info['pages'][0]['text'] for t in texts)
    assert all('Wrong' not in t and 'Vertical' not in t for t in texts)
    assert output.slides[1].shapes[0].image.blob==original
    assert not list(tmp_path.glob('smartppt-regions-*'))
    editable=next(s for s in output.slides[0].shapes if s.has_text_frame)
    editable.text='Edited 456.78';output.save(target)
    assert any(s.has_text_frame and s.text=='Edited 456.78' for s in Presentation(target).slides[0].shapes)
