from pathlib import Path
import pytest
from PIL import Image,ImageDraw,ImageFont,ImageChops
from smartppt.ocr_font import latin_font,CANDIDATES

DIRECTORY=Path('/System/Library/Fonts/Supplemental')
@pytest.mark.parametrize('family,filename,bold,italic',CANDIDATES)
def test_justified_word_spacing_does_not_change_font_family(family,filename,bold,italic):
 path=DIRECTORY/filename
 if not path.is_file():pytest.skip('optional installed-font acceptance')
 words='Annual revenue increased by 123.45 percent'.split();font=ImageFont.truetype(str(path),32)
 image=Image.new('RGB',(1300,80),'white');draw=ImageDraw.Draw(image);x=10
 for i,word in enumerate(words):
  draw.text((x,10),word,font=font,fill='black');x+=font.getlength(word)+[22,39,28,46][i%4]
 image=image.crop(ImageChops.difference(image,Image.new('RGB',image.size,'white')).getbbox())
 choice=latin_font(' '.join(words),image,(255,255,255),DIRECTORY)
 assert (choice['family'],choice['bold'],choice['italic'])==(family,bold,italic),choice
