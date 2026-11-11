from pathlib import Path
import pytest
from PIL import Image,ImageDraw,ImageFont
from smartppt.ocr_font import latin_font,CANDIDATES

DIRECTORY=Path('/System/Library/Fonts/Supplemental')


@pytest.mark.parametrize('family,filename,bold',CANDIDATES)
def test_glyph_comparison_preserves_serif_monospace_and_weight(family,filename,bold):
    path=DIRECTORY/filename
    if not path.exists():pytest.skip('optional installed-font acceptance; not required in portable CI')
    text='North revenue 123.45';font=ImageFont.truetype(str(path),40)
    l,t,r,b=font.getbbox(text);im=Image.new('RGB',(r-l,b-t),'white')
    ImageDraw.Draw(im).text((-l,-t),text,font=font,fill='black')
    # Use the actual non-white ink extent, as the OCR adapter does.
    from PIL import ImageChops
    im=im.crop(ImageChops.difference(im,Image.new('RGB',im.size,'white')).getbbox())
    result=latin_font(text,im,(255,255,255),DIRECTORY)
    assert (result['family'],result['bold'])==(family,bold)


def test_missing_fonts_and_unsupported_script_have_explicit_no_match(tmp_path):
    im=Image.new('RGB',(50,20),'white')
    assert latin_font('text',im,(255,255,255),tmp_path) is None
    assert latin_font('中文',im,(255,255,255),DIRECTORY) is None
