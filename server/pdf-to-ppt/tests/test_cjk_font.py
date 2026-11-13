import os
from pathlib import Path
import pytest
from PIL import Image,ImageDraw,ImageFont,ImageChops
from smartppt.ocr_font import latin_font

@pytest.mark.parametrize('family,key',[('Noto Sans SC','SMARTPPT_CJK_FONT'),('Noto Serif SC','SMARTPPT_CJK_SERIF_FONT')])
@pytest.mark.parametrize('bold',[False,True])
def test_cjk_family_and_weight_use_actual_variation_axis(family,key,bold):
 if not os.getenv(key):pytest.skip('optional pinned CJK fonts required')
 font=ImageFont.truetype(os.environ[key],40);font.set_variation_by_axes([700 if bold else 400]);text='本月营业收入123.45万元，增长12.8%。'
 l,t,r,b=font.getbbox(text);image=Image.new('RGB',(r-l,b-t),'white');ImageDraw.Draw(image).text((-l,-t),text,font=font,fill='black');image=image.crop(ImageChops.difference(image,Image.new('RGB',image.size,'white')).getbbox())
 choice=latin_font(text,image,(255,255,255),Path('/System/Library/Fonts/Supplemental'))
 assert (choice['family'],choice['bold'])==(family,bold),choice
 assert choice['matched']
