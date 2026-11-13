"""Optical character measurements never change atomic word ownership."""
from contextlib import closing
from copy import deepcopy
import pytest
import pypdfium2 as pdfium
from reportlab.pdfgen import canvas
from smartppt import regional


@pytest.fixture
def sample(tmp_path):
 path=tmp_path/'sample.pdf';c=canvas.Canvas(str(path));c.drawString(40,700,'North 123');c.save()
 with pdfium.PdfDocument(path) as doc,closing(doc[0]) as page:
  objects,_=regional.objects_for_page(page,word_regions=True)
  run=objects[0][1][0]
  with closing(page.get_textpage()) as tp:
   observed=[tp.get_charbox(i) for i in range(run['index'],run['end_index']) if not chr(pdfium.raw.FPDFText_GetUnicode(tp,i)).isspace()]
  yield page,run,observed


def test_median_resists_single_capital_height(sample):
 page,run,observed=sample;observed=list(observed)
 l,b,r,t=observed[0];observed[0]=(l,b,r,b+(t-b)*2)
 assert regional.character_height_ratio(page,run,run['text'].strip(),observed,1)==pytest.approx(1)
 assert regional.character_height_ratio(page,run,run['text'].strip(),observed,2)==pytest.approx(2)


@pytest.mark.parametrize('change',['text','count','owner','range','rotation','degenerate','nonfinite'])
def test_invalid_correspondence_rejected(sample,change):
 page,run,observed=sample;run=deepcopy(run);observed=list(observed);needle=run['text'].strip()
 if change=='text':needle='Wrong'
 if change=='count':observed.pop()
 if change=='owner':run['object_id']=-1
 if change=='range':run['end_index']=1000000
 if change=='rotation':run['rotation']=90
 if change=='degenerate':observed[0]=(0,0,1,0)
 if change=='nonfinite':observed[0]=(0,0,1,float('nan'))
 assert regional.character_height_ratio(page,run,needle,observed,1) is None


@pytest.mark.parametrize('code',[0,0xfffd,0xfffe,0xffff,0xfb01,0xe001,0xd800])
def test_unresolved_or_expanding_unicode_rejected(sample,monkeypatch,code):
 page,run,observed=sample;original=pdfium.raw.FPDFText_GetUnicode
 monkeypatch.setattr(pdfium.raw,'FPDFText_GetUnicode',lambda tp,i:code if i==run['index'] else original(tp,i))
 assert regional.character_height_ratio(page,run,run['text'].strip(),observed,1) is None


def test_rotated_page_rejected(sample,monkeypatch):
 page,run,observed=sample
 monkeypatch.setattr(page,'get_rotation',lambda:90)
 assert regional.character_height_ratio(page,run,run['text'].strip(),observed,1) is None


def test_character_mode_cannot_replace_existing_layout():
 with pytest.raises(ValueError,match='additive'):
  regional._recover_regions(None,None,[1],None,word_regions=True,character_fit=True)


def test_character_retry_failure_keeps_prior_report(monkeypatch):
 from smartppt import regional_order
 from smartppt.config import ConversionError
 prior={'source_ranges':[[0,4]],'regional_strategy':'source-words','warnings':[]}
 calls=[]
 def recover(*args,**kwargs):
  calls.append(kwargs)
  if kwargs.get('character_fit') and not kwargs.get('alternative_font') and not kwargs.get('normalize_tails'):raise ConversionError('render_failed','test')
  return {1:prior} if len(calls)==1 else {}
 monkeypatch.setattr(regional,'_recover_regions',recover)
 monkeypatch.setattr(regional_order,'restore_source_order',lambda *args:None)
 assert regional.recover_regions(None,None,[1],None)[1] is prior
 assert prior['warnings']==['additional_character_extension_unavailable']
 assert sum(bool(c.get('character_fit')) and not c.get('alternative_font') and not c.get('normalize_tails') for c in calls)==1
