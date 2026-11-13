from contextlib import closing
from io import BytesIO
import os
import numpy as np
import pypdfium2 as pdfium
from PIL import Image
from pptx import Presentation
from pptx.util import Pt
import pytest
from reportlab.pdfgen import canvas
from smartppt import regional


def fixture(path):
 c=canvas.Canvas(str(path),pagesize=(400,400));c.setFont('Helvetica',14)
 c.drawString(30,310,'North 123.45 South 678.90')
 c.drawString(30,50,'Footer 999');c.save()


def deck(page):
 prs=Presentation();prs.slide_width=prs.slide_height=Pt(400)
 slide=prs.slides.add_slide(prs.slide_layouts[6])
 objects,_=regional.objects_for_page(page,grouped=False)
 footer=[o for o in objects if all(r['box'][3]<100 for r in o[1])]
 regional.draw_objects(prs,slide,page,footer)
 return prs,slide,regional.covered_source_indices(page,footer)


def test_extension_changes_only_disjoint_approved_raster_rectangles(tmp_path):
 source=tmp_path/'source.pdf';fixture(source)
 with pdfium.PdfDocument(source) as doc,closing(doc[0]) as page:
  prs,slide,prior=deck(page);before=[s._element.xml for s in list(slide.shapes)[1:]]
  seed=regional.extension_seed(prs,slide,page);assert seed
  words,_=regional.objects_for_page(page,word_regions=True)
  chosen=regional.extension_candidates(page,words,prior,seed)
  assert chosen and all('Footer' not in r['text'] and '999' not in r['text'] for _,rs in chosen for r in rs)
  selected=chosen[:1];regional.draw_objects(prs,slide,page,selected,seed=seed)
  assert [s._element.xml for s in list(slide.shapes)[1:1+len(before)]]==before
  ids=[s.shape_id for s in slide.shapes];assert len(ids)==len(set(ids))
  actual=np.asarray(Image.open(BytesIO(slide.shapes[0].image.blob)));original=np.asarray(seed['background'])
  outside=np.ones(original.shape[:2],bool)
  for _,runs in selected:
   for run in runs:
    l,t,r,b=regional.word_pixel_box(run['box'],page.get_size());outside[t:b,l:r]=False
  assert np.array_equal(original[outside],actual[outside]) and not np.array_equal(original,actual)
  assert not prior.intersection(regional.covered_source_indices(page,selected))


def test_source_occurrence_and_rotated_box_are_both_protected(tmp_path):
 source=tmp_path/'source.pdf';fixture(source)
 with pdfium.PdfDocument(source) as doc,closing(doc[0]) as page:
  prs,slide,prior=deck(page);words,_=regional.objects_for_page(page,word_regions=True)
  seed=regional.extension_seed(prs,slide,page)
  # Even identical words elsewhere are independent occurrences.
  one=words[0];occurrence=regional.covered_source_indices(page,[one])
  assert not regional.extension_candidates(page,[one],occurrence,seed)
  shape=slide.shapes[1];shape.rotation=90;shape.left=Pt(20);shape.top=Pt(70);shape.width=Pt(100);shape.height=Pt(100)
  seed=regional.extension_seed(prs,slide,page)
  blocked=dict(one[1][0],box=[50,250,60,260])
  assert not regional.extension_candidates(page,[(one[0],[blocked])],set(),seed)


def test_extension_rejects_unrecognized_background_or_extra_graphics(tmp_path):
 source=tmp_path/'source.pdf';fixture(source)
 with pdfium.PdfDocument(source) as doc,closing(doc[0]) as page:
  prs,slide,_=deck(page);slide.shapes[0].crop_left=.01
  assert regional.extension_seed(prs,slide,page) is None
  slide.shapes[0].crop_left=0;slide.shapes[0].width+=Pt(1)
  assert regional.extension_seed(prs,slide,page) is None


def test_retained_text_must_remain_pixel_identical():
 prs=Presentation();prs.slide_width=prs.slide_height=Pt(100)
 a=Image.new('RGB',(200,200),'white');b=a.copy();seed={'protected_points':[(10,10,50,30)]}
 assert regional.retained_pixels_unchanged(seed,a,b,prs)
 b.putpixel((30,30),(0,0,0))
 assert not regional.retained_pixels_unchanged(seed,a,b,prs)
 assert not regional.retained_pixels_unchanged(seed,a,b.resize((100,100)),prs)


@pytest.mark.skipif(not os.getenv('SMARTPPT_TEST_RENDERER'),reason='real Office renderer required')
@pytest.mark.parametrize('initial_words',[False,True])
@pytest.mark.parametrize('character_fit',[False,True])
def test_real_extension_keeps_prior_xml_and_can_roll_back(tmp_path,monkeypatch,initial_words,character_fit):
 from smartppt.config import Settings
 source=tmp_path/'source.pdf';fixture(source);target=tmp_path/'result.pptx'
 with pdfium.PdfDocument(source) as doc,closing(doc[0]) as page:
  prs,slide,_=deck(page);regional.draw_objects(prs,slide,page,[]);prs.save(target)
 settings=Settings(renderer_path=os.environ['SMARTPPT_TEST_RENDERER'])
 original=regional.objects_for_page
 def footer(page,**kwargs):
  objects,warnings=original(page,**kwargs)
  return [o for o in objects if all(r['box'][3]<100 for r in o[1])],warnings
 monkeypatch.setattr(regional,'objects_for_page',footer)
 first=regional._recover_regions(source,target,[1],settings,word_regions=initial_words)
 assert first and first[1]['covered_source_glyphs']==9
 monkeypatch.setattr(regional,'objects_for_page',original)
 initial=target.read_bytes();xml=[s._element.xml for s in list(Presentation(target).slides[0].shapes)[1:]]
 added=regional._recover_regions(source,target,[1],settings,word_regions=True,minimum_coverage=first,extend=True,spacing_retry=character_fit,character_fit=character_fit)
 assert added and added[1]['covered_source_glyphs']>9
 assert [s._element.xml for s in list(Presentation(target).slides[0].shapes)[1:1+len(xml)]]==xml
 assert added[1]['retained_regions']==first[1]
 assert added[1]['added_editable_runs']>0
 assert added[1]['extension_calibration_mode']==('median-character-height' if character_fit else 'word-bounds')
 assert added[1]['baseline_render']==first[1]['baseline_render']
 # Final verification rejects a changed retained region, leaving the package
 # byte-identical even if individual new words already passed their gates.
 target.write_bytes(initial)
 monkeypatch.setattr(regional,'retained_pixels_unchanged',lambda *_:False)
 rejected=regional._recover_regions(source,target,[1],settings,word_regions=True,minimum_coverage=first,extend=True,spacing_retry=character_fit,character_fit=character_fit)
 assert rejected=={} and target.read_bytes()==initial


def test_observed_ink_protects_text_without_blocking_empty_textbox_space(tmp_path,monkeypatch):
 source=tmp_path/'source.pdf';fixture(source)
 with pdfium.PdfDocument(source) as doc,closing(doc[0]) as page:
  prs,slide,_=deck(page)
  seed=regional.extension_seed(prs,slide,page,source)
  assert seed and len(seed['protected_points'])==1
  l,t,r,b=seed['protected_points'][0]
  assert b-t<slide.shapes[1].height/12700
  import smartppt.ocr_fit as fit
  monkeypatch.setattr(fit,'observed_boxes',lambda *_:{})
  assert regional.extension_seed(prs,slide,page,source) is None



def test_source_words_route_still_gets_bounded_spacing_extension(monkeypatch):
 from smartppt import regional_order
 calls=[]
 prior={'source_ranges':[[10,20]],'regional_strategy':'source-words','warnings':[]}
 def recover(*args,**kwargs):
  calls.append(kwargs)
  if len(calls)==1:return {1:prior}
  if kwargs.get('extend'):assert kwargs['minimum_coverage'][1] is prior
  return {}
 monkeypatch.setattr(regional,'_recover_regions',recover)
 monkeypatch.setattr(regional_order,'restore_source_order',lambda *args:None)
 assert regional.recover_regions(None,None,[1],None)=={1:prior}
 retries=[c for c in calls if c.get('extend')]
 assert [c['spacing_retry'] for c in retries]==[True,False,True]
 assert [c.get('character_fit',False) for c in retries]==[False,False,True]
 assert all(c['word_regions'] for c in retries)
