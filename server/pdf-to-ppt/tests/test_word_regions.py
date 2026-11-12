from contextlib import closing
from io import BytesIO
import numpy as np
from PIL import Image
import pypdfium2 as pdfium
from pptx import Presentation
from pptx.util import Pt
from reportlab.pdfgen import canvas
from smartppt.layout import extract_native,page_background
from smartppt.regional import objects_for_page,regional_background,word_pixel_box,draw_objects
import pytest


def source(path,overlap=False):
    c=canvas.Canvas(str(path),pagesize=(400,400));c.setFont('Helvetica',16)
    c.setFillColorRGB(.85,.92,.98);c.rect(10,250,380,100,fill=1,stroke=0)
    c.setFillColorRGB(0,0,0)
    text=c.beginText(30,310);text.setWordSpace(10);text.textLine('North 123.45 South 678.90');c.drawText(text)
    if overlap:c.drawString(30,310,'OVERLAP')
    c.drawString(30,270,'Second line remains unchanged')
    c.save()


def test_words_preserve_source_order_and_full_object_identity(tmp_path):
    path=tmp_path/'words.pdf';source(path)
    with pdfium.PdfDocument(path) as doc,closing(doc[0]) as page:
        full,_,_=extract_native(page);words,_,_=extract_native(page,split_words=True)
        assert ''.join(r['text'] for r in words)==''.join(r['text'] for r in full)
        first=[r for r in words if r['object_id']==full[0]['object_id']]
        assert [r['text'].strip() for r in first]==['North','123.45','South','678.90']


def test_selected_word_keeps_other_words_and_colored_background(tmp_path):
    path=tmp_path/'words.pdf';source(path)
    with pdfium.PdfDocument(path) as doc,closing(doc[0]) as page:
        objects,_=objects_for_page(page,word_regions=True)
        selected=[o for o in objects if o[1][0]['text'].strip()=='123.45']
        assert len(selected)==1
        before=page_background(page,[],max_side=2200,scale_limit=2)
        after=regional_background(page,selected);box=word_pixel_box(selected[0][1][0]['box'],page.get_size())
        a,b=np.asarray(before),np.asarray(after);mask=np.ones(a.shape[:2],dtype=bool)
        l,t,r,bottom=box;mask[t:bottom,l:r]=False
        assert np.array_equal(a[mask],b[mask]) and not np.array_equal(a,b)
        # Removing only the selected number restores the actual blue paper.
        paper=b[t:bottom,l:r];assert np.ptp(paper,axis=(0,1)).max()<=1
        assert np.array_equal(a,np.asarray(page_background(page,[],max_side=2200,scale_limit=2)))
        prs=Presentation();prs.slide_width=Pt(400);prs.slide_height=Pt(400)
        slide=prs.slides.add_slide(prs.slide_layouts[6]);draw_objects(prs,slide,page,selected)
        assert [s.text.strip() for s in slide.shapes if s.has_text_frame]==['123.45']
        assert np.array_equal(np.asarray(Image.open(BytesIO(slide.shapes[0].image.blob))),b)


def test_overlapping_words_from_different_objects_are_not_candidates(tmp_path):
    path=tmp_path/'overlap.pdf';source(path,overlap=True)
    with pdfium.PdfDocument(path) as doc,closing(doc[0]) as page:
        objects,_=objects_for_page(page,word_regions=True)
        texts=[r['text'].strip() for _,runs in objects for r in runs]
        assert 'North' not in texts and 'OVERLAP' not in texts
        assert '678.90' in texts


def test_ambiguous_mapping_keeps_ink_and_does_not_discard_other_words(tmp_path,monkeypatch):
    path=tmp_path/'ambiguous.pdf';source(path)
    get_unicode=pdfium.raw.FPDFText_GetUnicode
    # A broken ToUnicode mapping changes extracted text, not the visible glyph.
    monkeypatch.setattr(pdfium.raw,'FPDFText_GetUnicode',lambda tp,i:2 if i==0 else get_unicode(tp,i))
    with pdfium.PdfDocument(path) as doc,closing(doc[0]) as page:
        strict,_,warnings=extract_native(page,split_words=True)
        assert not any('123.45' in r['text'] for r in strict)
        assert 'unmapped_glyph_kept_as_graphic' in warnings
        assert 'rotated_text_kept_as_graphic' not in warnings
        objects,_=objects_for_page(page,word_regions=True)
        selected=[o for o in objects if o[1][0]['text'].strip()=='123.45']
        assert len(selected)==1
        assert not any(r['text'].strip()=='orth' for _,runs in objects for r in runs)
        before=np.asarray(page_background(page,[],max_side=2200,scale_limit=2))
        after=np.asarray(regional_background(page,selected))
        l,t,r,b=word_pixel_box(selected[0][1][0]['box'],page.get_size())
        mask=np.ones(before.shape[:2],dtype=bool);mask[t:b,l:r]=False
        assert np.array_equal(before[mask],after[mask])
        assert not np.array_equal(before,after)
        assert all('\x02' not in run['text'] for _,runs in objects for run in runs)


def test_partial_extraction_cannot_be_used_for_full_object_removal():
    with pytest.raises(ValueError,match='word isolation'):
        extract_native(None,partial_regions=True)


def test_word_retry_only_visits_pages_without_verified_results(monkeypatch):
    import smartppt.regional as regional
    calls=[]
    def recover(source,target,pages,settings,grouped=False,word_regions=False):
        calls.append((pages,grouped,word_regions))
        return {3:{'route':'native-regions'}} if word_regions else {2:{'route':'native-regions'}} if grouped else {1:{'route':'native-regions'}}
    monkeypatch.setattr(regional,'_recover_regions',recover)
    assert set(regional.recover_regions(None,None,[1,2,3],None))=={1,2,3}
    assert calls==[([1,2,3],False,False),([2,3],True,False),([3],False,True)]


@pytest.mark.skipif(not __import__('os').getenv('SMARTPPT_TEST_RENDERER'),reason='real Office renderer required')
def test_actual_word_recovery_preserves_other_glyphs_and_content(tmp_path,settings):
    import os
    from smartppt.regional import _recover_regions
    from smartppt.layout import add_background
    path=tmp_path/'source.pdf';source(path);target=tmp_path/'result.pptx'
    prs=Presentation();prs.slide_width=Pt(400);prs.slide_height=Pt(400);slide=prs.slides.add_slide(prs.slide_layouts[6])
    with pdfium.PdfDocument(path) as doc,closing(doc[0]) as page:
        add_background(slide,page_background(page,[],max_side=2200,scale_limit=2),400,400)
    prs.save(target);settings.renderer_path=os.environ['SMARTPPT_TEST_RENDERER']
    result=_recover_regions(path,target,[1],settings,word_regions=True)
    assert result and result[1]['regional_strategy']=='source-words'
    text=[s.text.strip() for s in Presentation(target).slides[0].shapes if s.has_text_frame]
    assert text and set(text)<=set('North 123.45 South 678.90 Second line remains unchanged'.split())
    assert result[1]['editable_runs']==len(text)
    assert not list(tmp_path.glob('smartppt-regions-*'))
