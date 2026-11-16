from contextlib import closing
from hashlib import sha256
from types import SimpleNamespace
import os
import pytest
import pypdfium2 as pdfium
from pptx import Presentation
from pptx.util import Pt
from reportlab.pdfgen import canvas
from smartppt.layout import add_text
from smartppt.config import ConversionError
from smartppt.final_words import source_targets,try_finalize_words


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_source_binding_tracks_final_shape_splits_and_page_rotation(tmp_path,rotation):
    source=tmp_path/'source.pdf';c=canvas.Canvas(str(source),pagesize=(400,300));c.drawString(40,200,'Alpha 123 Beta');c.save()
    with pdfium.PdfDocument(source) as doc,closing(doc[0]) as page:
        page.set_rotation(rotation);width,height=page.get_size()
        prs=Presentation();prs.slide_width=Pt(width);prs.slide_height=Pt(height);slide=prs.slides.add_slide(prs.slide_layouts[6])
        for text in ['Alpha ','123 ','Beta']:add_text(slide,text,10,10,100,20,12)
        rows=source_targets(prs,1,page)
        assert len(rows)==3 and [r['shape'] for r in rows]==[0,1,2]
        assert all(0<=r['bbox'][0]<r['bbox'][2]<=width and 0<=r['bbox'][1]<r['bbox'][3]<=height for r in rows)
        a,b=rows[0]['bbox'],rows[-1]['bbox']
        if rotation==0:assert a[2]<b[0]
        elif rotation==90:assert a[3]<b[1]
        elif rotation==180:assert b[2]<a[0]
        else:assert b[3]<a[1]
        slide.shapes[1].text='124 '
        assert source_targets(prs,1,page) is None


def test_optional_final_render_failure_keeps_package_and_existing_report(tmp_path,settings,monkeypatch):
    import smartppt.final_words as module
    source=tmp_path/'source.pdf';c=canvas.Canvas(str(source));c.drawString(40,200,'Alpha 123');c.save()
    prs=Presentation();slide=prs.slides.add_slide(prs.slide_layouts[6]);add_text(slide,'Alpha 123',40,100,100,20,12)
    target=tmp_path/'target.pptx';prs.save(target);before=sha256(target.read_bytes()).hexdigest()
    report={'pages':[{'page':1,'text_granularity':'word','warnings':[]}]}
    def fail(*args,**kwargs):raise ConversionError('layout_render_failed')
    monkeypatch.setattr(module,'render_presentations',fail)
    try_finalize_words(source,target,report,settings)
    assert sha256(target.read_bytes()).hexdigest()==before
    assert report['final_word_geometry_error']=='layout_render_failed'
    assert report['pages'][0]['final_word_geometry']=={'accepted':False,'error':'layout_render_failed','full_package_rendered':False}


def test_source_crop_origin_is_applied_to_final_glyph_positions(tmp_path):
    source=tmp_path/'source.pdf';c=canvas.Canvas(str(source),pagesize=(400,300));c.drawString(40,200,'Alpha');c.save()
    prs=Presentation();prs.slide_width=Pt(400);prs.slide_height=Pt(300)
    slide=prs.slides.add_slide(prs.slide_layouts[6]);add_text(slide,'Alpha',40,100,100,20,12)
    with pdfium.PdfDocument(source) as doc,closing(doc[0]) as page:
        before=source_targets(prs,1,page)[0]['bbox']
        page.set_cropbox(20,30,380,280);prs.slide_width=Pt(360);prs.slide_height=Pt(250)
        after=source_targets(prs,1,page)[0]['bbox']
    assert after==pytest.approx([before[0]-20,before[1]-20,before[2]-20,before[3]-20])


@pytest.mark.parametrize('excluded',[True,False])
def test_graphic_marker_is_skipped_only_when_pdfium_excludes_it_from_source_text(monkeypatch,excluded):
    tp=SimpleNamespace(get_text_range=lambda:'ABC',count_chars=lambda:4,close=lambda:None,
                       get_charbox=lambda i:(10+i*10,20,18+i*10,30))
    page=SimpleNamespace(get_size=lambda:(100,100),get_bbox=lambda:(0,0,100,100),
                         get_rotation=lambda:0,get_textpage=lambda:tp)
    monkeypatch.setattr(pdfium.raw,'FPDFText_GetUnicode',lambda _,i:[65,66,2,67][i])
    monkeypatch.setattr(pdfium.raw,'FPDFText_GetTextIndexFromCharIndex',lambda _,i:-1 if i==2 and excluded else i)
    prs=Presentation();prs.slide_width=prs.slide_height=Pt(100);slide=prs.slides.add_slide(prs.slide_layouts[6])
    add_text(slide,'AB',10,70,20,20,12);add_text(slide,'C',40,70,10,20,12)
    rows=source_targets(prs,1,page)
    if excluded:assert [r['bbox'] for r in rows]==[(10,70,28,80),(40,70,48,80)]
    else:assert rows is None


@pytest.mark.skipif(not os.getenv('SMARTPPT_TEST_RENDERER'),reason='real Office renderer required')
@pytest.mark.parametrize('allow_change',[True,False])
def test_finished_package_is_refitted_and_reopened_without_changing_text(tmp_path,settings,monkeypatch,allow_change):
    from smartppt.render_gate import render_presentations
    from smartppt.final_words import measure,passed
    settings.renderer_path=os.environ['SMARTPPT_TEST_RENDERER']
    prs=Presentation();prs.slide_width=Pt(400);prs.slide_height=Pt(300)
    for texts in [('Alpha 123','Beta 456'),('Another page 789',)]:
        slide=prs.slides.add_slide(prs.slide_layouts[6])
        for i,text in enumerate(texts):add_text(slide,text,30,30+i*30,200,24,12)
    source_ppt=tmp_path/'source.pptx';prs.save(source_ppt)
    source=render_presentations([source_ppt],tmp_path,settings)[0]
    prs.slides[0].shapes[0].left+=Pt(3);prs.slides[0].shapes[1].top+=Pt(3)
    target=tmp_path/'target.pptx';prs.save(target);before_text=[[s.text for s in slide.shapes] for slide in prs.slides]
    before=sha256(target.read_bytes()).hexdigest()
    if not allow_change:monkeypatch.setattr('smartppt.final_words.accept_candidate',lambda *args:False)
    report={'pages':[{'page':i,'text_granularity':'word','warnings':[]} for i in [1,2]]}
    try_finalize_words(source,target,report,settings)
    if not allow_change:
        assert sha256(target.read_bytes()).hexdigest()==before
        assert not report['pages'][0]['final_word_geometry']['accepted']
        assert report['pages'][1]['final_word_geometry']['accepted']
        return
    assert all(p['final_word_geometry']['accepted'] for p in report['pages'])
    assert report['pages'][0]['final_word_geometry']['calibration_passes']>0
    actual=Presentation(target);assert [[s.text for s in slide.shapes] for slide in actual.slides]==before_text
    rendered=render_presentations([target],tmp_path,settings)[0];targets={}
    with pdfium.PdfDocument(source) as doc:
        for n in [1,2]:
            with closing(doc[n-1]) as page:targets[n]=source_targets(actual,n,page)
    assert all(passed(result) for result in measure(actual,rendered,targets).values())
