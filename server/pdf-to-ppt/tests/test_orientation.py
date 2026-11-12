import hashlib,json
from pathlib import Path
import pytest
from PIL import Image,ImageDraw
from pptx import Presentation
from pptx.util import Pt
from smartppt.config import ConversionError,Settings
from smartppt.orientation import validate_orientation,restore_shapes,prepare_images


def pair(tmp_path,angle):
    source=tmp_path/'source.png';target=tmp_path/'result.png'
    image=Image.new('RGB',(80,120),'white');ImageDraw.Draw(image).rectangle((3,8,17,29),fill='red');image.save(source)
    image.rotate(angle,expand=True).save(target)
    record={'angle':angle,'confidence':.95,'input_size':[80,120],
            'input_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'output_sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
    return source,target,record


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_lossless_transpose_and_orientation(tmp_path,angle):
    source,target,record=pair(tmp_path,angle)
    assert validate_orientation(source,target,record)==angle


@pytest.mark.parametrize('field,value',[('angle',True),('angle',45),('confidence',float('nan')),('confidence',.8),('input_size',[120,80]),('input_sha256','changed')])
def test_untrusted_orientation_rejected(tmp_path,field,value):
    source,target,record=pair(tmp_path,90);record[field]=value
    with pytest.raises(ConversionError):validate_orientation(source,target,record)


def test_digest_alone_cannot_authorize_changed_pixels(tmp_path):
    source,target,record=pair(tmp_path,90)
    Image.new('RGB',(120,80),'white').save(target);record['output_sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
    with pytest.raises(ConversionError,match='orientation_pixels_mismatch'):validate_orientation(source,target,record)


@pytest.mark.parametrize('angle,expected',[(0,(30,25)),(90,(95,30)),(180,(50,95)),(270,(25,50))])
def test_inverse_maps_shape_center_and_keeps_editable_text(angle,expected):
    prs=Presentation();slide=prs.slides.add_slide(prs.slide_layouts[6])
    shape=slide.shapes.add_textbox(Pt(10),Pt(15),Pt(40),Pt(20));shape.text='Total 123.45';shape.rotation=3
    restore_shapes(slide,angle,Pt(80),Pt(120))
    assert ((shape.left+shape.width/2)/12700,(shape.top+shape.height/2)/12700)==pytest.approx(expected)
    assert shape.rotation==pytest.approx((3+angle)%360) and shape.text=='Total 123.45'


def test_disabled_orientation_preserves_cached_inputs(tmp_path):
    images={0:tmp_path/'original.png'}
    assert prepare_images(images,tmp_path,Settings(orientation_runner=''))==(images,{})


def test_preprocessor_missing_and_invalid_outputs(tmp_path,monkeypatch):
    import sys
    with pytest.raises(ConversionError,match='orientation_not_configured'):
        prepare_images({0:tmp_path/'source.png'},tmp_path,Settings(orientation_runner='missing',ocr_python=sys.executable))
    runner=tmp_path/'runner.py';runner.write_text('')
    monkeypatch.setattr('smartppt.orientation.subprocess.run',lambda *a,**kw:None)
    with pytest.raises(ConversionError,match='invalid_orientation_result'):
        prepare_images({0:tmp_path/'source.png'},tmp_path,Settings(orientation_runner=str(runner),ocr_python=sys.executable))
