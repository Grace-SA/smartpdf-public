import hashlib,json,math,os,subprocess,sys,time
from pathlib import Path
from io import BytesIO
from copy import deepcopy
import pytest
import pypdfium2 as pdfium
from pptx import Presentation
from pptx.util import Pt
from PIL import Image
from reportlab.pdfgen import canvas
from smartppt.config import ConversionError
from smartppt.layout import convert_native,extract_native,font_family
from smartppt.assisted import validate_ocr,verify_agreement,content_error,scan_page,ocr_slide,safe_table
from smartppt.quality import inspect_pptx
from smartppt.pdf import inspect_pdf
from smartppt.worker import stop_worker
from smartppt.render_gate import accept_candidate,compare_and_restore,run_gate


def test_native_text_and_page_order(pdf_file,tmp_path):
    out=tmp_path/'out.pptx';report=convert_native(pdf_file,out)
    quality=inspect_pptx(out,inspect_pdf(pdf_file),'editable')
    assert len(report)==2
    assert not [w for w in quality['warnings'] if w['code'] in ('text_mismatch','numeric_mismatch')]
    assert all(r['editable_runs'] for r in report)


def test_scaled_font_matrix_and_bold(tmp_path):
    source=tmp_path/'scaled.pdf';c=canvas.Canvas(str(source));c.scale(12,12);c.setFont('Helvetica-Bold',1);c.drawString(4,50,'Scaled 123');c.save()
    with pdfium.PdfDocument(source) as doc:
        runs,_,_=extract_native(doc[0])
        assert runs[0]['size']==pytest.approx(12)
        assert runs[0]['bold']


def test_page_rotation_cancels_text_rotation(tmp_path):
    from pypdf import PdfReader,PdfWriter
    raw=tmp_path/'raw.pdf';source=tmp_path/'rotated.pdf'
    c=canvas.Canvas(str(raw),pagesize=(400,600));c.translate(100,100);c.rotate(90);c.setFont('Helvetica',12);c.drawString(0,0,'Rotated 123.45');c.save()
    writer=PdfWriter(clone_from=raw);writer.pages[0].rotate(90);writer.write(source)
    with pdfium.PdfDocument(source) as doc:
        runs,_,_=extract_native(doc[0]);assert ''.join(r['text'] for r in runs)=='Rotated 123.45'
        assert runs[0]['size']==pytest.approx(12)
        l,b,r,t=runs[0]['box'];assert r-l>t-b


def test_font_mapping(monkeypatch):
    monkeypatch.delenv('SMARTPPT_CJK_SERIF_FONT',raising=False)
    assert font_family('SimSun','中文')[0]=='Noto Sans SC'
    assert font_family('Times-Roman','123')[0]=='Times New Roman'
    assert font_family('Courier','123')[0]=='Courier New'


def test_optional_cjk_serif_keeps_latin_in_same_family(tmp_path,monkeypatch):
    path=tmp_path/'operator-font.ttf';path.write_bytes(b'font availability only; embedding separately checks the pinned hash')
    monkeypatch.setenv('SMARTPPT_CJK_SERIF_FONT',str(path))
    for name in ('Songti SC','SimSun','ABCDEF+MingLiU','Noto Serif SC'):
        for text in ('English 123.45','中文预算'):
            assert font_family(name,text)[0]=='Noto Serif SC'
    assert font_family('Helvetica','English')[0]=='Arial'
    assert font_family('Unknown','中文')[0]=='Noto Sans SC'
    path.unlink()
    assert font_family('SimSun','中文')[0]=='Noto Sans SC'


def sample_record(tmp_path):
    path=tmp_path/'image.png';Image.new('RGB',(100,50),'white').save(path)
    return path,{'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'image_size':[100,50],
        'lines':[{'text':'Total 123.45','confidence':.99,'polygon':[[5,5],[95,5],[95,30],[5,30]]}]}


@pytest.mark.parametrize('invalid',['nan','outside','confidence','digest','dimensions'])
def test_ocr_rejects_untrusted_geometry(tmp_path,invalid):
    path,record=sample_record(tmp_path)
    if invalid=='nan':record['lines'][0]['polygon'][0][0]=math.nan
    if invalid=='outside':record['lines'][0]['polygon'][0][0]=-5
    if invalid=='confidence':record['lines'][0]['confidence']=1.5
    if invalid=='digest':record['input_sha256']='wrong'
    if invalid=='dimensions':record['image_size']=[50,100]
    with pytest.raises(ConversionError):validate_ocr(record,path)


def test_model_disagreement_and_token_limit(tmp_path):
    path,record=sample_record(tmp_path)
    verifier={'input_sha256':record['input_sha256'],'capped':False,'blocks':[{'label':'text','content':'Total 123.45'}]}
    assert verify_agreement(record,verifier,path)
    verifier['blocks'][0]['content']='Total 123.54'
    assert not verify_agreement(record,verifier,path)
    verifier['blocks'][0]['content']='Total 123.45';verifier['capped']=True
    assert not verify_agreement(record,verifier,path)


def test_numeric_weight_and_whitespace():
    assert content_error('金额 123.45','金额123.45')==0
    assert content_error('金额123.45','金额123.54')>0


@pytest.mark.parametrize('new,accepted',[
    ({'mae':.01,'foreground_mae':.12},True),
    ({'mae':.04,'foreground_mae':.12},False),
    ({'mae':.01,'foreground_mae':.31},False)])
def test_visual_regression_is_rejected(new,accepted):
    assert accept_candidate({'mae':.03,'foreground_mae':.2},new)==accepted


def test_render_gate_restores_original_image_relationship(tmp_path,monkeypatch):
    baseline=tmp_path/'baseline.pptx';candidate=tmp_path/'candidate.pptx'
    red=tmp_path/'red.png';blue=tmp_path/'blue.png';Image.new('RGB',(30,30),'red').save(red);Image.new('RGB',(30,30),'blue').save(blue)
    p=Presentation();s=p.slides.add_slide(p.slide_layouts[6]);s.shapes.add_picture(str(red),Pt(10),Pt(10));p.save(baseline)
    p=Presentation(baseline);s=p.slides[0]
    for shape in list(s.shapes):shape._element.getparent().remove(shape._element)
    s.shapes.add_picture(str(blue),Pt(10),Pt(10));p.save(candidate)
    monkeypatch.setattr('smartppt.render_gate.metric',lambda source,pdf,index:{'mae':.01 if pdf=='old' else .2,'foreground_mae':.1 if pdf=='old' else .5})
    report={'pages':[{'route':'native-coordinate','warnings':[]}]}
    compare_and_restore(baseline,candidate,None,report,'old','new')
    assert Presentation(candidate).slides[0].shapes[0].image.blob==red.read_bytes()
    assert report['pages'][0]['route']=='stirling-retained-visual'


def test_missing_renderer_fails_closed(settings):
    settings.renderer_path=''
    with pytest.raises(ConversionError,match='layout_renderer_not_configured'):
        run_gate(None,None,None,{'pages':[{'route':'native-coordinate'}]},settings)


def test_image_only_and_invisible_ocr_routing(tmp_path):
    image=tmp_path/'scan.png';Image.new('RGB',(300,400),'white').save(image)
    for invisible in [False,True]:
        path=tmp_path/f'{invisible}.pdf';c=canvas.Canvas(str(path),pagesize=(300,400));c.drawImage(str(image),0,0,300,400)
        if invisible:
            text=c.beginText(20,350);text.setTextRenderMode(3);text.textLine('stale hidden OCR layer');c.drawText(text)
        c.save()
        with pdfium.PdfDocument(path) as d:assert scan_page(d[0])


def test_model_disagreement_does_not_erase_page(pdf_file,tmp_path):
    path,record=sample_record(tmp_path);prs=Presentation();prs.slide_width=Pt(100);prs.slide_height=Pt(72)
    slide=prs.slides.add_slide(prs.slide_layouts[6])
    with pdfium.PdfDocument(pdf_file) as d:result=ocr_slide(prs,slide,d[0],path,record,False)
    assert result['editable_lines']==0
    assert 'ocr_models_disagree_kept_as_image' in result['warnings']
    assert len(slide.shapes)==1 and slide.shapes[0].shape_type==13


def test_empty_pixels_never_get_hallucinated_text(pdf_file,tmp_path):
    path,record=sample_record(tmp_path);prs=Presentation();slide=prs.slides.add_slide(prs.slide_layouts[6])
    with pdfium.PdfDocument(pdf_file) as d:result=ocr_slide(prs,slide,d[0],path,record,True)
    assert result['editable_lines']==0
    assert 'no_visible_ink_kept_as_image' in result['warnings']


def test_table_retained_only_when_content_and_bounds_match():
    prs=Presentation();slide=prs.slides.add_slide(prs.slide_layouts[6])
    shape=slide.shapes.add_table(1,2,Pt(10),Pt(10),Pt(100),Pt(20));shape.table.cell(0,0).text='Total';shape.table.cell(0,1).text='123.45'
    assert safe_table(slide,'Total 123.45')
    assert not safe_table(slide,'Total 123.54')
    shape.left=prs.slide_width
    assert not safe_table(slide,'Total 123.45')


@pytest.mark.skipif(os.name!='posix',reason='POSIX process group behavior')
def test_cancel_terminates_ocr_descendants(tmp_path):
    marker=tmp_path/'should-not-exist';ready=tmp_path/'ready'
    grandchild="import time;from pathlib import Path;time.sleep(1);Path(%r).touch()"%str(marker)
    parent="import subprocess,sys,time;from pathlib import Path;subprocess.Popen([sys.executable,'-c',%r]);Path(%r).touch();time.sleep(30)"%(grandchild,str(ready))
    child=subprocess.Popen([sys.executable,'-c',parent],start_new_session=True)
    try:
        deadline=time.monotonic()+5
        while not ready.exists() and time.monotonic()<deadline:time.sleep(.02)
        assert ready.exists();stop_worker(child);time.sleep(1.1)
        assert not marker.exists()
    finally:
        if child.poll() is None:stop_worker(child)
