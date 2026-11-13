import os
import pytest
from copy import deepcopy
from contextlib import closing
import pypdfium2 as pdfium
from pptx import Presentation
from pptx.util import Pt
from reportlab.pdfgen import canvas
from smartppt.config import Settings
from smartppt.layout import add_background,page_background
from smartppt.regional import compact_source_ranges


def test_coverage_ranges_preserve_gaps_and_occurrences():
 assert compact_source_ranges({1,2,3,7,9,10})==[[1,4],[7,8],[9,11]]


@pytest.mark.skipif(not os.getenv('SMARTPPT_TEST_RENDERER'),reason='real Office renderer required')
def test_finer_strategy_must_keep_footer_occurrence_on_each_page(tmp_path,monkeypatch):
 import smartppt.regional as regional
 source=tmp_path/'source.pdf';c=canvas.Canvas(str(source),pagesize=(400,400))
 for body in ['North 123.45 South 678.90','Body Footer 999 repeated']:
  c.setFont('Helvetica',14);c.drawString(30,300,body);c.drawString(30,50,'Footer 999');c.showPage()
 c.save();target=tmp_path/'result.pptx';p=Presentation();p.slide_width=Pt(400);p.slide_height=Pt(400)
 with pdfium.PdfDocument(source) as doc:
  for i in range(2):
   with closing(doc[i]) as page:add_background(p.slides.add_slide(p.slide_layouts[6]),page_background(page,[],max_side=2200,scale_limit=2),400,400)
 p.save(target);settings=Settings(renderer_path=os.environ['SMARTPPT_TEST_RENDERER'])
 objects=regional.objects_for_page;geometry=regional.rendered_word_regions;recover=regional._recover_regions;saved={}
 def candidates(page,grouped=True,word_regions=False,word_clusters=False,cluster_mode='adjacent'):
  result,warnings=objects(page,grouped=grouped,word_regions=word_regions,word_clusters=word_clusters,cluster_mode=cluster_mode)
  if not word_regions:result=[o for o in result if all(r['box'][3]<100 for r in o[1])]
  return result,warnings
 def boxes(prs,number,page,objects,pdf,**kwargs):
  result=geometry(prs,number,page,objects,pdf,**kwargs)
  # Simulate a failed footer fit on page two. The identical body occurrence
  # must never stand in for this source occurrence in the coverage check.
  if number==2:
   # Also reject all new words in an extension; its retained footer is never
   # re-fitted, so a failed footer replacement alone should not reject it.
   if kwargs.get('shape_offset'):return [None]*len(objects)
   for i,(_,runs) in enumerate(objects):
    if all(r['box'][3]<100 for r in runs):result[i]=None
  return result
 def run(*args,**kwargs):
  result=recover(*args,**kwargs)
  if not kwargs.get('grouped') and not kwargs.get('word_regions'):
   saved['reports']=deepcopy(result);before=Presentation(target)
   saved['second_xml']=before.slides[1]._element.xml
   saved['second_image']=before.slides[1].shapes[0].image.blob
  return result
 monkeypatch.setattr(regional,'objects_for_page',candidates)
 monkeypatch.setattr(regional,'rendered_word_regions',boxes)
 # This test isolates monotonic provenance/rollback, not pixel thresholds.
 monkeypatch.setattr(regional,'score_regions',lambda a,b,boxes,p:[{'mae':0,'foreground_mae':0} for _ in boxes] if boxes else None)
 monkeypatch.setattr(regional,'acceptable_page',lambda *_:True)
 monkeypatch.setattr(regional,'_recover_regions',run)
 report=regional.recover_regions(source,target,[1,2],settings)
 assert report[1]['covered_source_glyphs']>saved['reports'][1]['covered_source_glyphs']
 prior={i for a,b in saved['reports'][1]['source_ranges'] for i in range(a,b)}
 current={i for a,b in report[1]['source_ranges'] for i in range(a,b)}
 assert prior<current and report[1]['regional_strategy']=='source-words'
 assert report[2]==saved['reports'][2]
 final=Presentation(target)
 assert final.slides[1]._element.xml==saved['second_xml']
 assert final.slides[1].shapes[0].image.blob==saved['second_image']


def test_interleaved_object_indices_are_not_claimed_by_another_run(tmp_path):
 import ctypes
 from smartppt.layout import extract_native
 from smartppt.regional import covered_source_indices
 source=tmp_path/'objects.pdf';c=canvas.Canvas(str(source),pagesize=(400,400));c.drawString(30,300,'North');c.drawString(30,200,'South');c.save()
 with pdfium.PdfDocument(source) as doc,closing(doc[0]) as page:
  runs,objects,_=extract_native(page);first=dict(runs[0]);first['end_index']=runs[-1]['end_index']
  lookup={ctypes.cast(o.raw,ctypes.c_void_p).value:o for o in objects}
  actual=covered_source_indices(page,[([lookup[first['object_id']]],[first])])
  assert actual==set(range(runs[0]['index'],runs[0]['end_index']))
  assert not actual.intersection(range(runs[-1]['index'],runs[-1]['end_index']))

