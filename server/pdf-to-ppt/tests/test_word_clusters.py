"""Connected overlap candidates are atomic; never recover unsafe subcomponents."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from smartppt.word_clusters import connected_word_clusters
from smartppt import regional


def parts(count=3):
 owner=object();result=[]
 for i in range(count):
  result.append((owner,{'text':'A ' if i<count-1 else 'B','index':i*2,'end_index':i*2+2,
   'box':[10+i*11,40,20+i*11,50],'baseline':40.,'size':12.,'rotation':0,
   'font':'Arial','source_font':'Helvetica','source_base_font':'Helvetica',
   'bold':False,'italic':False,'color':(0,0,0),'object_id':id(owner),'blocked_boxes':[]}))
 return result


def geometry(items):
 boxes=[(r['box'][0]-2,r['box'][1]-2,r['box'][2]+2,r['box'][3]+2) for _,r in items]
 neighbors=[{j for j,b in enumerate(boxes) if regional.intersects(a,b)} for a in boxes]
 return boxes,neighbors


def clusters(items,blocked=()):
 boxes,neighbors=geometry(items)
 return connected_word_clusters(items,boxes,neighbors,list(blocked))


def test_transitive_component_keeps_text_order_and_unique_owner():
 original=parts();before=deepcopy([r for _,r in original]);shuffled=[original[2],original[0],original[1]]
 result=clusters(shuffled)
 assert len(result)==1 and result[0][0]==[original[0][0]]
 assert [(r['text'],r['index'],r['end_index']) for r in result[0][1]]==[(r['text'],r['index'],r['end_index']) for _,r in original]
 assert [r for _,r in original]==before
 assert all(r['source_region'] for r in result[0][1])


@pytest.mark.parametrize('count',[1,9])
def test_singletons_and_oversized_components_not_partitioned(count):
 assert clusters(parts(count))==[]


def test_maximum_eight_members_remains_atomic():
 result=clusters(parts(8));assert len(result)==1 and len(result[0][1])==8


@pytest.mark.parametrize('change',[
 {'font':'Other'},{'source_font':'Other'},{'source_base_font':'Other'},
 {'bold':True},{'italic':True},{'color':(1,0,0)},{'size':12.01},
 {'baseline':40.11},{'baseline':None},{'rotation':90},
 {'index':5},{'text':'A\n'},{'text':'A\t'},{'text':'A'},
])
def test_incompatible_middle_invalidates_whole_component(change):
 items=parts();items[1][1].update(change)
 assert clusters(items)==[]


def test_small_baseline_rounding_tolerance():
 items=parts();items[1][1]['baseline']=40.09
 assert len(clusters(items))==1


def test_blocked_middle_does_not_create_safe_endpoints():
 items=parts();assert clusters(items,[(22,42,23,48)])==[]


def test_real_ink_overlap_or_reverse_x_rejected():
 items=parts();items[1][1]['box'][0]=19
 assert clusters(items)==[]
 items=parts();items[0][1]['box'],items[1][1]['box']=items[1][1]['box'],items[0][1]['box']
 assert clusters(items)==[]


def test_character_and_width_bounds():
 items=parts(2);items[0][1]['text']='A'*158+' ';items[0][1]['end_index']=159
 items[1][1].update(index=159,end_index=160)
 assert clusters(items)==[]
 items=parts(2);items[0][1]['box']=[10,40,110,50];items[1][1]['box']=[111,40,211,50]
 assert clusters(items)==[]


def test_disjoint_valid_component_not_lost_with_invalid_component():
 a=parts(2);b=parts(2)
 for _,r in b:r['box']=[r['box'][0]+100,r['box'][1],r['box'][2]+100,r['box'][3]];r['index']+=10;r['end_index']+=10
 a[0][1]['bold']=True
 result=clusters(a+b)
 assert len(result)==1 and result[0][1][0]['index']==10


def test_different_owners_preserved_without_double_removal():
 items=parts();owner=object();items[1]=(owner,items[1][1]);items[1][1]['object_id']=id(owner)
 result=clusters(items)
 assert len(result)==1 and len(result[0][0])==2 and result[0][0][0] is items[0][0]


def test_existing_occurrence_or_protected_member_blocks_entire_cluster():
 items=parts();candidate=clusters(items)
 assert candidate
 page=SimpleNamespace(get_size=lambda:(100,100))
 assert regional.extension_candidates(page,candidate,{2},{'protected':[]})==[]
 protected=regional.word_pixel_box(items[1][1]['box'],page.get_size())
 assert regional.extension_candidates(page,candidate,set(),{'protected':[protected]})==[]


def literal_pdf(path,cropped=False,obstacle=False):
 from reportlab.pdfgen import canvas
 from pypdf import PdfReader,PdfWriter
 c=canvas.Canvas(str(path),pagesize=(400,400));c.setFont('Helvetica',5)
 c.drawString(140,250,'AA AA')
 if obstacle:
  c.setFillAlpha(.5);c.drawString(143,250,'X')
 c.save()
 if cropped:
  reader=PdfReader(path);reader.pages[0].cropbox.lower_left=(100,100);reader.pages[0].cropbox.upper_right=(300,300)
  writer=PdfWriter();writer.add_page(reader.pages[0]);writer.write(path)


def test_literal_source_provenance_and_generated_space_rejection(tmp_path,monkeypatch):
 from contextlib import closing
 import pypdfium2 as pdfium
 from smartppt.layout import extract_native
 from smartppt.word_clusters import source_verified
 path=tmp_path/'literal.pdf';literal_pdf(path)
 with pdfium.PdfDocument(path) as doc,closing(doc[0]) as page:
  runs,_,_=extract_native(page,split_words=True,partial_regions=True)
  assert source_verified(page,runs)
  assert not source_verified(page,[dict(runs[0],text='wrong')])
  assert not source_verified(page,[dict(runs[0],object_id=-1)])
  original=pdfium.raw.FPDFText_IsGenerated
  space=runs[0]['end_index']-1
  monkeypatch.setattr(pdfium.raw,'FPDFText_IsGenerated',lambda tp,i:1 if i==space else original(tp,i))
  assert not source_verified(page,runs)


def test_cropped_unsafe_neighbor_remains_protected(tmp_path):
 from contextlib import closing
 import pypdfium2 as pdfium
 plain=tmp_path/'plain.pdf';blocked=tmp_path/'blocked.pdf'
 literal_pdf(plain,cropped=True);literal_pdf(blocked,cropped=True,obstacle=True)
 with pdfium.PdfDocument(plain) as doc,closing(doc[0]) as page:
  candidates,_=regional.objects_for_page(page,word_regions=True,word_clusters=True)
  assert candidates,'safe small-font literal words should form one cluster'
 with pdfium.PdfDocument(blocked) as doc,closing(doc[0]) as page:
  candidates,_=regional.objects_for_page(page,word_regions=True,word_clusters=True)
  assert candidates==[]


def test_cluster_mode_requires_additive_word_recovery():
 with pytest.raises(ValueError,match='additive'):
  regional._recover_regions(None,None,[1],None,word_regions=True,word_clusters=True)
 with pytest.raises(ValueError,match='regional words'):
  regional.objects_for_page(None,word_clusters=True)


def collision(items):
 boxes,neighbors=geometry(items)
 return connected_word_clusters(items,boxes,neighbors,[],mode='collision')


def test_collision_keeps_noncontiguous_multiline_runs_separate():
 items=parts(2);items[0][1]['text']='123';items[0][1]['end_index']=3
 items[1][1].update(text='123',index=20,end_index=23,box=[10,51,20,61],baseline=51.)
 result=collision(list(reversed(items)))
 assert len(result)==1
 assert [(r['text'],r['index'],r['box']) for r in result[0][1]]==[(r['text'],r['index'],r['box']) for _,r in items]
 assert clusters(items)==[]


@pytest.mark.parametrize('change',[
 {'index':1}, {'box':[10,49,20,59]}, {'box':[10,51,20,101]},
 {'bold':True},{'baseline':float('nan')},{'rotation':90},
])
def test_collision_rejects_index_ink_height_style_or_rotation(change):
 items=parts(2);items[1][1].update(index=20,end_index=23,box=[10,51,20,61],baseline=51.)
 items[1][1].update(change)
 assert collision(items)==[]


def collision_pdf(path):
 from reportlab.pdfgen import canvas
 c=canvas.Canvas(str(path),pagesize=(200,200));c.setFont('Helvetica',14)
 c.drawString(40,140,'123');c.drawString(100,80,'OMITTED');c.drawString(40,128.5,'123')
 c.drawString(100,140,'456');c.drawString(100,128.5,'456')
 c.setFont('Helvetica',14);c.drawString(20,20,'Footer 999');c.save()


def test_collision_and_independent_drawing_are_identical_and_keep_gap_raster(tmp_path):
 from contextlib import closing
 import numpy as np
 import pypdfium2 as pdfium
 from pptx import Presentation
 from pptx.util import Pt
 path=tmp_path/'collision.pdf';collision_pdf(path)
 with pdfium.PdfDocument(path) as doc,closing(doc[0]) as page:
  candidates,_=regional.objects_for_page(page,word_regions=True,word_clusters=True,cluster_mode='collision')
  assert len(candidates)==2 and [len(runs) for _,runs in candidates]==[2,2]
  assert [[r['text'] for r in runs] for _,runs in candidates]==[['123','123'],['456','456']]
  independent=[(group,[run]) for group,runs in candidates for run in runs]
  assert np.array_equal(np.asarray(regional.regional_background(page,candidates)),np.asarray(regional.regional_background(page,independent)))
  original=regional.page_background(page,[],max_side=2200,scale_limit=2.0)
  background=regional.regional_background(page,candidates)
  # Intervening source text is not editable and retains its raster exactly.
  outside=np.ones(np.asarray(original).shape[:2],dtype=bool)
  for _,runs in candidates:
   for run in runs:
    l,t,r,b=regional.word_pixel_box(run['box'],page.get_size());outside[t:b,l:r]=False
  assert np.array_equal(np.asarray(original)[outside],np.asarray(background)[outside])
  omitted=np.asarray(original.crop((195,215,330,245)))
  assert (omitted.min(axis=2)<128).any(), 'omitted word ROI must contain actual ink'
  assert np.array_equal(omitted,np.asarray(background.crop((195,215,330,245))))
  decks=[]
  for objects in (candidates,independent):
   prs=Presentation();prs.slide_width=prs.slide_height=Pt(200);slide=prs.slides.add_slide(prs.slide_layouts[6])
   regional.draw_objects(prs,slide,page,objects);decks.append(slide)
  assert [s._element.xml for s in decks[0].shapes]==[s._element.xml for s in decks[1].shapes]
  assert regional.covered_source_indices(page,candidates)==regional.covered_source_indices(page,independent)


@pytest.mark.skipif(not __import__('os').getenv('SMARTPPT_TEST_RENDERER'),reason='real renderer required')
def test_real_collision_atomic_rejection_retention_and_source_order(tmp_path,monkeypatch):
 import os
 from contextlib import closing
 import pypdfium2 as pdfium
 from pptx import Presentation
 from smartppt.config import Settings
 from smartppt.pdf import inspect_pdf
 from smartppt.preserve import convert_preserve
 from smartppt.regional_order import restore_source_order
 from smartppt.quality import numeric_tokens,shape_text
 path=tmp_path/'collision.pdf';collision_pdf(path);target=tmp_path/'candidate.pptx'
 convert_preserve(path,target,inspect_pdf(path));settings=Settings(renderer_path=os.environ['SMARTPPT_TEST_RENDERER'])
 original=regional.objects_for_page
 def footer(page,**kwargs):
  objects,warnings=original(page,**kwargs)
  return [o for o in objects if all(r['box'][3]<40 for r in o[1])],warnings
 monkeypatch.setattr(regional,'objects_for_page',footer)
 prior=regional._recover_regions(path,target,[1],settings,word_regions=True)
 assert prior[1]['covered_source_glyphs']==9
 monkeypatch.setattr(regional,'objects_for_page',original)
 before=target.read_bytes();xml=[s._element.xml for s in list(Presentation(target).slides[0].shapes)[1:]]
 kwargs=dict(word_regions=True,word_clusters=True,cluster_mode='collision',minimum_coverage=prior,extend=True,spacing_retry=True,character_fit=True)
 added=regional._recover_regions(path,target,[1],settings,**kwargs)
 assert added and added[1]['covered_source_glyphs']==21
 assert added[1]['added_word_clusters']==2
 assert added[1]['retained_regions']==prior[1] and added[1]['baseline_render']==prior[1]['baseline_render']
 assert [s._element.xml for s in list(Presentation(target).slides[0].shapes)[1:1+len(xml)]]==xml
 expected=numeric_tokens('123 123 456 456 999')
 assert numeric_tokens('\n'.join(shape_text(Presentation(target).slides[0].shapes)))==expected
 restore_source_order(path,target,added,settings)
 assert added[1]['source_reading_order_verified']
 mapping=added[1]['source_shape_indices'];indices=added[1]['source_run_indices']
 assert sorted(mapping)==list(range(1,len(indices)+1))
 assert [index for _,index in sorted(zip(mapping,indices))]==sorted(indices)
 assert numeric_tokens('\n'.join(shape_text(Presentation(target).slides[0].shapes)))==expected
 # Exercise the delivered embedded font and actual rendered text, not only XML.
 from collections import Counter
 from smartppt import base_font
 from smartppt.font_embedding import bundled_payloads,embed_noto
 from smartppt.render_gate import render_presentations
 from smartppt.quality import normalized
 embedded=tmp_path/'embedded.pptx'
 expected_text='\n'.join(shape_text(Presentation(target).slides[0].shapes))
 embed_noto(target,embedded,bundled_payloads(family=base_font.FAMILY),base_font.FAMILY)
 rendered=render_presentations([embedded],tmp_path,settings)[0]
 with pdfium.PdfDocument(rendered) as doc,closing(doc[0]) as page,closing(page.get_textpage()) as tp:
  actual=tp.get_text_range()
  assert numeric_tokens(actual)==expected
  assert Counter(normalized(actual))==Counter(normalized(expected_text))
  assert 'OMITTED' not in actual
  names=[o.get_font().get_base_name() for o in page.get_objects(filter=[pdfium.raw.FPDF_PAGEOBJ_TEXT])]
  assert names and all('SmartPDFBaseSans' in name for name in names)
 # Reject one member in the first pair. Candidate-level scoring must retain
 # neither word of that pair, rather than saving its other matching number.
 target.write_bytes(before);calibrate=regional.calibrate_runs
 def move_one_member(prs,number,page,objects,rendered,**options):
  calibrate(prs,number,page,objects,rendered,**options)
  # Actually misplace one glyph run, leaving its paired run unchanged.
  for _,runs in objects:
   if len(runs)==2 and runs[0]['box'][0]<80:
    assert 'fit' in runs[0]
    runs[0]['fit']['x']+=5
    break
 monkeypatch.setattr(regional,'calibrate_runs',move_one_member)
 partial=regional._recover_regions(path,target,[1],settings,**kwargs)
 assert partial and partial[1]['covered_source_glyphs']==15 and partial[1]['added_word_clusters']==1
 assert numeric_tokens('\n'.join(shape_text(Presentation(target).slides[0].shapes)))==numeric_tokens('456 456 999')
 monkeypatch.setattr(regional,'calibrate_runs',calibrate)
 target.write_bytes(before);monkeypatch.setattr(regional,'retained_pixels_unchanged',lambda *_:False)
 assert regional._recover_regions(path,target,[1],settings,**kwargs)=={}
 assert target.read_bytes()==before


def test_dense_adjacency_abstains_before_quadratic_storage():
 from smartppt.word_clusters import bounded_neighbors
 visits=[]
 def memberships():
  for i in range(3000):
   visits.append(i)
   if len(visits)>34:raise AssertionError('dense graph consumed beyond link budget')
   yield ['dense']
 assert bounded_neighbors(memberships(),{'dense':set(range(3000))}) is None
 assert len(visits)==34
 assert bounded_neighbors([['a'],['b']],{'a':{0},'b':{1}},max_links=2)==[{0},{1}]
 assert bounded_neighbors([['a'],['b']],{'a':{0},'b':{1}},max_links=1) is None


def test_cluster_run_limit_precedes_pixel_graph(tmp_path,monkeypatch):
 from contextlib import closing
 import pypdfium2 as pdfium
 from smartppt.word_clusters import MAX_PAGE_RUNS
 path=tmp_path/'runs.pdf';literal_pdf(path)
 with pdfium.PdfDocument(path) as doc,closing(doc[0]) as page:
  runs,objects,_=regional.extract_native(page,split_words=True,partial_regions=True)
  monkeypatch.setattr(regional,'extract_native',lambda *a,**k:([dict(runs[0]) for _ in range(MAX_PAGE_RUNS+1)],objects,[]))
  monkeypatch.setattr(regional,'word_pixel_box',lambda *a:pytest.fail('pixel graph allocated before run guard'))
  result,warnings=regional.objects_for_page(page,word_regions=True,word_clusters=True,cluster_mode='collision')
  assert result==[] and warnings==['word_cluster_resource_limit']


def test_source_count_limit_precedes_admission_and_does_not_change_isolated_mode(tmp_path,monkeypatch):
 from contextlib import closing
 import pypdfium2 as pdfium
 from smartppt import word_clusters
 path=tmp_path/'chars.pdf';literal_pdf(path)
 monkeypatch.setattr(word_clusters,'MAX_SOURCE_CHARS',1)
 monkeypatch.setattr(word_clusters,'source_verified',lambda *a:pytest.fail('source verification ran beyond character budget'))
 with pdfium.PdfDocument(path) as doc,closing(doc[0]) as page:
  result,warnings=regional.objects_for_page(page,word_regions=True,word_clusters=True,cluster_mode='collision')
  assert result==[] and warnings==['word_cluster_resource_limit']
  _,warnings=regional.objects_for_page(page,word_regions=True)
  assert 'word_cluster_resource_limit' not in warnings


def test_resource_warning_propagates_without_rendering_or_target_mutation(tmp_path,monkeypatch):
 from smartppt.config import Settings
 from smartppt.pdf import inspect_pdf
 from smartppt.preserve import convert_preserve
 source=tmp_path/'source.pdf';literal_pdf(source);target=tmp_path/'target.pptx'
 convert_preserve(source,target,inspect_pdf(source));before=target.read_bytes()
 prior={1:{'source_ranges':[[0,1]],'warnings':[]}}
 monkeypatch.setattr(regional,'objects_for_page',lambda *a,**k:([],['word_cluster_resource_limit']))
 monkeypatch.setattr(regional,'render_presentations',lambda *a,**k:pytest.fail('resource-abstained page must not render'))
 for _ in range(2):
  assert regional._recover_regions(source,target,[1],Settings(),word_regions=True,word_clusters=True,cluster_mode='collision',extend=True,minimum_coverage=prior)=={}
 assert prior[1]['warnings']==['word_cluster_resource_limit'] and target.read_bytes()==before


def test_resource_flagged_page_skipped_in_all_later_cluster_attempts(monkeypatch):
 from smartppt import regional_order
 monkeypatch.setattr(regional.shutil,'which',lambda name:'/test/pdftoppm')
 prior={n:{'source_ranges':[[0,1]],'warnings':[]} for n in (1,2)};calls=[];first=True
 def recover(source,target,pages,settings,**kwargs):
  nonlocal first
  if first:first=False;return prior
  if kwargs.get('word_clusters'):
   calls.append(list(pages))
   if len(calls)==1:prior[1]['warnings'].append('word_cluster_resource_limit')
  return {}
 monkeypatch.setattr(regional,'_recover_regions',recover)
 monkeypatch.setattr(regional_order,'restore_source_order',lambda *a:None)
 result=regional.recover_regions(None,None,[1,2],None)
 assert calls==[[1,2],[2],[2],[2],[2],[2]] # original four plus normalized-tail two
 assert result[1] is prior[1] and result[1]['warnings']==['word_cluster_resource_limit']
