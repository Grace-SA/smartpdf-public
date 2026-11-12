import hashlib,os
from copy import deepcopy
import pytest
from pptx import Presentation
from pptx.util import Pt
from reportlab.pdfgen import canvas
from smartppt.config import ConversionError
from smartppt.native_words import try_native_words
from contextlib import closing
import pypdfium2 as pdfium
from smartppt.layout import extract_native
from smartppt.native_words import join_word_fragments


def test_source_number_fragments_are_joined_without_merging_words(tmp_path):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    source=tmp_path/'fragments.pdf';c=canvas.Canvas(str(source),pagesize=(400,400));c.setFont('Helvetica',14)
    x=30
    for value in ['Article ', 'II.', '21', '.2', ' costs ', '201', '2']:
        c.drawString(x,300,value);x+=stringWidth(value,'Helvetica',14)
    c.drawString(30,260,'Separate 123');c.save()
    with pdfium.PdfDocument(source) as doc,closing(doc[0]) as page:
        runs,_,_=extract_native(page,split_words=True)
        joined=join_word_fragments(runs)
        assert [r['text'].strip() for r in joined]==['Article','II.21.2','costs','2012','Separate','123']
        assert len(joined[1]['object_ids'])==3
        assert ''.join(r['text'] for r in runs)==''.join(r['text'] for r in joined)


@pytest.mark.skipif(not os.getenv('SMARTPPT_TEST_RENDERER'),reason='real Office renderer required')
def test_recovered_fragmented_numbers_survive_content_gate(tmp_path,settings):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from smartppt.pdf import inspect_pdf
    from smartppt.content_gate import enforce_content_safety
    source=tmp_path/'fragments.pdf';c=canvas.Canvas(str(source),pagesize=(400,400));c.setFont('Helvetica',14)
    x=30
    for value in ['Article ', 'II.', '21', '.2', ' costs ', '201', '2']:
        c.drawString(x,300,value);x+=stringWidth(value,'Helvetica',14)
    c.save();target=tmp_path/'candidate.pptx';p=Presentation();p.slide_width=Pt(400);p.slide_height=Pt(400)
    slide=p.slides.add_slide(p.slide_layouts[6]);slide.shapes.add_textbox(Pt(10),Pt(10),Pt(100),Pt(30)).text='Wrong 999';p.save(target)
    settings.renderer_path=os.environ['SMARTPPT_TEST_RENDERER'];report={'pages':[{'page':1,'route':'stirling-retained'}]}
    try_native_words(source,target,report,settings)
    enforce_content_safety(source,target,inspect_pdf(source),report,settings)
    assert report['pages'][0]['route']=='native-coordinate'
    assert [s.text.strip() for s in Presentation(target).slides[0].shapes if s.has_text_frame]==['Article','II.21.2','costs','2012']


def test_failed_optional_retry_cannot_publish_unwritten_metadata(monkeypatch,settings):
    import smartppt.native_words as module
    def fail(source,target,report,settings):
        report['pages'][0]['route']='native-coordinate'
        raise ConversionError('layout_render_failed')
    monkeypatch.setattr(module,'repair_native_words',fail)
    report={'pages':[{'page':1,'route':'stirling-retained'}]}
    try_native_words(None,None,report,settings)
    assert report['pages'][0]['route']=='stirling-retained'
    assert report['word_layout_error']=='layout_render_failed'


@pytest.mark.skipif(not os.getenv('SMARTPPT_TEST_RENDERER'),reason='real Office renderer required')
def test_justified_words_recover_complete_text_and_reject_page_independently(tmp_path,settings,monkeypatch):
    import smartppt.native_words as module
    source=tmp_path/'source.pdf';c=canvas.Canvas(str(source),pagesize=(400,400))
    for _ in range(2):
        c.setFont('Times-Roman',14)
        for y in range(60,350,32):
            t=c.beginText(30,y);t.setWordSpace(8);t.textLine('North 123.45 South 678.90');c.drawText(t)
        c.showPage()
    c.save();target=tmp_path/'candidate.pptx';p=Presentation();p.slide_width=Pt(400);p.slide_height=Pt(400)
    for _ in range(2):
        slide=p.slides.add_slide(p.slide_layouts[6]);slide.shapes.add_textbox(Pt(200),Pt(300),Pt(100),Pt(40)).text='Wrong 999'
    p.save(target);old=Presentation(target).slides[1].shapes[0]._element.xml
    settings.renderer_path=os.environ['SMARTPPT_TEST_RENDERER'];calls=[];gate=module.accept_candidate
    def accept(a,b):calls.append(1);return len(calls)==1 and gate(a,b)
    monkeypatch.setattr(module,'accept_candidate',accept)
    report={'pages':[{'page':n,'route':'stirling-retained'} for n in [1,2]]}
    try_native_words(source,target,report,settings)
    assert report['pages'][0]['route']=='native-coordinate' and report['pages'][0]['text_granularity']=='word'
    assert report['pages'][0]['word_layout_attempt']['position_passed']==40
    assert report['pages'][1]['route']=='stirling-retained'
    out=Presentation(target)
    assert out.slides[1].shapes[0]._element.xml==old
    assert [s.text.strip() for s in out.slides[0].shapes if s.has_text_frame]==['North','123.45','South','678.90']*10
    assert not list(tmp_path.glob('smartppt-word-layout-*'))
    # A later retry must preserve an already-correct page even when another
    # page is repaired and the shared presentation package is saved again.
    first_xml=out.slides[0]._element.xml
    monkeypatch.setattr(module,'accept_candidate',gate)
    again={'pages':[{'page':1,'route':'native-coordinate'},{'page':2,'route':'stirling-retained'}]}
    try_native_words(source,target,again,settings)
    assert Presentation(target).slides[0]._element.xml==first_xml
    assert again['pages'][1]['route']=='native-coordinate'


def test_unsupported_angle_is_not_claimed_as_complete(tmp_path,settings):
    source=tmp_path/'source.pdf';c=canvas.Canvas(str(source),pagesize=(400,400))
    c.drawString(30,300,'Visible 123.45');c.saveState();c.translate(100,100);c.rotate(45);c.drawString(0,0,'Angled 678.90');c.restoreState();c.save()
    target=tmp_path/'candidate.pptx';p=Presentation();p.slides.add_slide(p.slide_layouts[6]);p.save(target)
    before=hashlib.sha256(target.read_bytes()).hexdigest();report={'pages':[{'page':1,'route':'stirling-retained'}]};original=deepcopy(report)
    try_native_words(source,target,report,settings)
    assert report==original and hashlib.sha256(target.read_bytes()).hexdigest()==before


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('page_rotation',[0,90,180,270])
def test_rotated_word_baseline_accounts_for_page_rotation(tmp_path,angle,page_rotation):
    from pypdf import PdfReader,PdfWriter
    source=tmp_path/'rotation.pdf';c=canvas.Canvas(str(source),pagesize=(400,600))
    c.translate(200,300);c.rotate(angle);c.drawString(0,0,'North 123.45');c.save()
    if page_rotation:
        writer=PdfWriter();writer.add_page(PdfReader(source).pages[0].rotate(page_rotation))
        with source.open('wb') as stream:writer.write(stream)
    with pdfium.PdfDocument(source) as doc,closing(doc[0]) as page:
        runs,_,warnings=extract_native(page,split_words=True,allow_quarter_turns=True)
        assert [r['text'].strip() for r in runs]==['North','123.45']
        assert all(r['rotation']==(page_rotation-angle)%360 for r in runs)
        assert 'rotated_text_kept_as_graphic' not in warnings


@pytest.mark.skipif(not os.getenv('SMARTPPT_TEST_RENDERER'),reason='real Office renderer required')
def test_quarter_turns_survive_actual_office_reconstruction(tmp_path,settings):
    source=tmp_path/'quarter.pdf';c=canvas.Canvas(str(source),pagesize=(400,400))
    for angle in [0,90,180,270]:
        c.saveState();c.translate(200,200);c.rotate(angle);c.drawString(0,0,'North 123.45');c.restoreState();c.showPage()
    c.save();target=tmp_path/'result.pptx';p=Presentation();p.slide_width=Pt(400);p.slide_height=Pt(400)
    for _ in range(4):
        s=p.slides.add_slide(p.slide_layouts[6]);s.shapes.add_textbox(Pt(20),Pt(20),Pt(100),Pt(20)).text='Wrong 999'
    p.save(target);settings.renderer_path=os.environ['SMARTPPT_TEST_RENDERER']
    report={'pages':[{'page':i+1,'route':'stirling-retained'} for i in range(4)]}
    try_native_words(source,target,report,settings)
    assert all(r['route']=='native-coordinate' for r in report['pages'])
    result=Presentation(target)
    for slide,angle in zip(result.slides,[0,90,180,270]):
        shapes=[s for s in slide.shapes if s.has_text_frame]
        assert [s.text.strip() for s in shapes]==['North','123.45']
        assert all(s.rotation==(-angle)%360 for s in shapes)
