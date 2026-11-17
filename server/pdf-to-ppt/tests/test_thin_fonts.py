import os,struct
from io import BytesIO
from pathlib import Path
import pytest
from PIL import Image,ImageDraw,ImageFont,ImageChops
from fontTools.ttLib import TTFont
from smartppt.ocr_font import latin_font
from smartppt.font_embedding import bundled_payloads

@pytest.mark.parametrize('base,key',[('Noto Sans SC','SMARTPPT_CJK_FONT'),('Noto Serif SC','SMARTPPT_CJK_SERIF_FONT')])
@pytest.mark.parametrize('text',['项目预算123.45元，增长12.8%。','Revenue was 123.45 in November.'])
def test_thin_face_preserves_family_for_cjk_and_latin(base,key,text):
 if not os.getenv(key):pytest.skip('optional pinned CJK font required')
 font=ImageFont.truetype(os.environ[key],40);font.set_variation_by_axes([100]);l,t,r,b=font.getbbox(text)
 image=Image.new('RGB',(r-l,b-t),'white');ImageDraw.Draw(image).text((-l,-t),text,font=font,fill='black');image=image.crop(ImageChops.difference(image,Image.new('RGB',image.size,'white')).getbbox())
 choice=latin_font(text,image,(255,255,255),Path('/System/Library/Fonts/Supplemental'))
 assert choice['family']==('SmartPDF Sans100' if base=='Noto Sans SC' else 'SmartPDF Serif200') and choice['weight']==(100 if base=='Noto Sans SC' else 200) and not choice['bold'],choice

@pytest.mark.parametrize('family,key',[('SmartPDF Sans100','SMARTPPT_CJK_FONT'),('SmartPDF Serif200','SMARTPPT_CJK_SERIF_FONT')])
def test_thin_static_payload_has_matching_family_and_complete_glyphs(family,key):
 if not os.getenv(key):pytest.skip('optional pinned CJK font required')
 data=bundled_payloads(False,family)['regular'];size=struct.unpack_from('<I',data,4)[0]
 with TTFont(BytesIO(data[-size:])) as font:
  assert font['name'].getDebugName(1)==font['name'].getDebugName(16)==family
  assert font['name'].getDebugName(2)==font['name'].getDebugName(17)=='Regular'
  assert font['OS/2'].usWeightClass==(100 if family=='SmartPDF Sans100' else 200) and font['OS/2'].fsType==0
  assert 'fvar' not in font
  assert set(map(ord,'项目预算123.45Revenue'))<=set(font.getBestCmap())
  assert 'PREAMBLE' in font['name'].getDebugName(13)
