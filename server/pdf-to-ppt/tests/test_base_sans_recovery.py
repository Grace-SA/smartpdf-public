"""A licensed alternative font may only add strictly verified regular words."""
from contextlib import closing
from copy import deepcopy
from collections import Counter
import os
import pytest
import pypdfium2 as pdfium
from pptx import Presentation
from reportlab.pdfgen import canvas
from smartppt import regional,base_font
from smartppt.config import Settings,ConversionError
from smartppt.pdf import inspect_pdf
from smartppt.preserve import convert_preserve


def run(**changes):
 result={'text':'Revenue 123.45','source_base_font':'HelveticaNeueLTStd-Roman','bold':False,'italic':False,'font':'Arial','substituted':True}
 result.update(changes);return result


@pytest.mark.parametrize('name',['Helvetica','HelveticaNeueLTStd-Roman','ABCDEF+HelveticaNeueLTStd-Roman'])
def test_exact_regular_names_select_substitute_without_mutating_input(name):
 original=run(source_base_font=name);before=deepcopy(original)
 selected=regional.alternative_base_sans([(['object'],[original])])
 assert selected[0][1][0]['font']==base_font.FAMILY
 assert selected[0][1][0]['substituted'] and original==before


@pytest.mark.parametrize('change',[
 {'source_base_font':'HelveticaNeueLTStd-Bd'}, {'source_base_font':'HelveticaNeue'},
 {'source_base_font':'Helvetica-Bold'}, {'source_base_font':'Arial'},
 {'source_base_font':'HelveticaNeueLTStd-RomanFake'}, {'source_base_font':'ABCDE+Helvetica'},
 {'bold':True},{'italic':True},{'rotation':90},{'font':base_font.FAMILY},
 {'text':'预算'},{'text':'e\u0301'},{'text':'\u2003'},{'text':'   '},
])
def test_unsupported_source_style_or_unicode_stays_raster(change):
 assert regional.alternative_base_sans([(['object'],[run(**change)])])==[]


def test_both_raw_and_nfkc_cmap_are_required(monkeypatch):
 monkeypatch.setattr(base_font,'approved_cmap',lambda:{ord('①'):'onecircle'})
 assert regional.alternative_base_sans([(['object'],[run(text='①')])])==[]


@pytest.mark.parametrize('kwargs',[{'alternative_font':'unknown','extend':True,'spacing_retry':True,'word_regions':True},{'alternative_font':'base-sans'},{'alternative_font':'base-sans','extend':True,'word_regions':True}])
def test_alternative_cannot_replace_existing_layout(kwargs):
 with pytest.raises(ValueError):regional._recover_regions(None,None,[1],None,**kwargs)


def test_optional_font_failure_preserves_prior_and_stops_bounded_retry(monkeypatch):
 from smartppt import regional_order
 prior={'source_ranges':[[0,5]],'warnings':[]};calls=[]
 def recover(*args,**kwargs):
  calls.append(kwargs)
  if kwargs.get('alternative_font'):raise ConversionError('portable_base_font_integrity_failed')
  return {1:prior} if len(calls)==1 else {}
 monkeypatch.setattr(regional,'_recover_regions',recover)
 monkeypatch.setattr(regional_order,'restore_source_order',lambda *args:None)
 assert regional.recover_regions(None,None,[1],None)[1] is prior
 assert prior['warnings']==['additional_base_sans_extension_unavailable']
 assert sum(bool(c.get('alternative_font')) for c in calls)==1


@pytest.mark.skipif(not os.getenv('SMARTPPT_TEST_RENDERER'),reason='real renderer required')
@pytest.mark.parametrize('character_fit',[True,False])
def test_actual_substitute_extension_retains_xml_baseline_and_rollback(tmp_path,monkeypatch,character_fit):
 source=tmp_path/'source.pdf';c=canvas.Canvas(str(source),pagesize=(400,400));c.setFont('Helvetica',14)
 c.drawString(30,310,'North 123.45 South 678.90');c.drawString(30,50,'Footer 999');c.save()
 target=tmp_path/'candidate.pptx';convert_preserve(source,target,inspect_pdf(source))
 settings=Settings(renderer_path=os.environ['SMARTPPT_TEST_RENDERER']);original=regional.objects_for_page
 def footer(page,**kwargs):
  objects,warnings=original(page,**kwargs)
  return [o for o in objects if all(r['box'][3]<100 for r in o[1])],warnings
 monkeypatch.setattr(regional,'objects_for_page',footer)
 prior=regional._recover_regions(source,target,[1],settings,word_regions=True)
 assert prior[1]['covered_source_glyphs']==9
 prior[1]['warnings'].extend(['retained_test_warning','reviewed_font_substitute_not_source_identity'])
 def substitute_candidates(page,**kwargs):
  objects,warnings=original(page,**kwargs)
  # Deliberately exercise substitution, not source-identical Helvetica selection.
  for _,runs in objects:
   for r in runs:r.update(source_base_font='HelveticaNeueLTStd-Roman',font='Arial')
  return objects,warnings
 monkeypatch.setattr(regional,'objects_for_page',substitute_candidates)
 before=target.read_bytes();xml=[s._element.xml for s in list(Presentation(target).slides[0].shapes)[1:]]
 kwargs=dict(word_regions=True,minimum_coverage=prior,extend=True,spacing_retry=True,character_fit=character_fit,alternative_font='base-sans')
 result=regional._recover_regions(source,target,[1],settings,**kwargs)
 assert result[1]['covered_source_glyphs']>9
 assert result[1]['retained_regions']==prior[1]
 assert result[1]['baseline_render']==prior[1]['baseline_render']
 assert result[1]['calibration_font']==base_font.FAMILY
 assert 'retained_test_warning' in result[1]['warnings']
 assert result[1]['extension_font_strategy']=='base-sans-substitute'
 assert result[1]['warnings'].count('reviewed_font_substitute_not_source_identity')==1
 assert [s._element.xml for s in list(Presentation(target).slides[0].shapes)[1:1+len(xml)]]==xml
 # Alternative recovered words must survive the actual embedded-font path,
 # not merely the pre-embedding host font renderer.
 from smartppt.font_embedding import bundled_payloads,embed_noto
 from smartppt.render_gate import render_presentations
 from smartppt.quality import normalized,shape_text,numeric_tokens
 embedded=tmp_path/'embedded.pptx'
 expected='\n'.join(shape_text(Presentation(target).slides[0].shapes))
 embed_noto(target,embedded,bundled_payloads(family=base_font.FAMILY),base_font.FAMILY)
 rendered=render_presentations([embedded],tmp_path,settings)[0]
 with pdfium.PdfDocument(rendered) as doc,closing(doc[0]) as page,closing(page.get_textpage()) as tp:
  actual=tp.get_text_range()
  assert Counter(normalized(actual))==Counter(normalized(expected))
  assert numeric_tokens(actual)==numeric_tokens(expected)
  names=[o.get_font().get_base_name() for o in page.get_objects(filter=[pdfium.raw.FPDF_PAGEOBJ_TEXT])]
  assert names and all('SmartPDFBaseSans' in name for name in names)
 target.write_bytes(before);monkeypatch.setattr(regional,'retained_pixels_unchanged',lambda *_:False)
 assert regional._recover_regions(source,target,[1],settings,**kwargs)=={}
 assert target.read_bytes()==before
