import pytest
from pptx import Presentation
from smartppt.layout import add_text
from smartppt.ocr_fit import fit_local


def text_shape(angle):
    prs=Presentation();slide=prs.slides.add_slide(prs.slide_layouts[6])
    shape=add_text(slide,'中文倾斜报告保留准确文字和数字123.45',40,50,300,24,12.5)
    shape.rotation=angle
    return shape


@pytest.mark.parametrize('angle',[2,358,88,92,178,182,268,272])
@pytest.mark.parametrize('height_error',[-.50004,0,.50004])
def test_skew_pixel_height_noise_preserves_font_size(angle,height_error):
    shape=text_shape(angle);text=shape.text
    # A long line is slightly too wide and displaced; its height differs only
    # by one raster pixel plus rotation serialization noise.
    desired=(40,50,340,62.5)
    actual=(41,48,349,60.5+height_error)
    assert fit_local(shape,desired,actual)
    run=shape.text_frame.paragraphs[0].runs[0]
    assert run.font.size.pt==12.5
    assert int(run._r.get_or_add_rPr().get('spc'))<0
    assert shape.rotation==angle and shape.text==text


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_quarter_turn_optical_sizing_is_unchanged(angle):
    shape=text_shape(angle)
    assert fit_local(shape,(40,50,340,62.5),(40,50,340,63))
    assert shape.text_frame.paragraphs[0].runs[0].font.size.pt==pytest.approx(12.5*12.5/13,abs=.011)


@pytest.mark.parametrize('difference',[-1,-.502,.502,1])
def test_real_height_error_still_changes_skew_font_size(difference):
    shape=text_shape(2)
    assert fit_local(shape,(40,50,340,62.5),(40,50,340,62.5+difference))
    assert shape.text_frame.paragraphs[0].runs[0].font.size.pt==pytest.approx(12.5*12.5/(12.5+difference),abs=.011)


@pytest.mark.parametrize('actual',[(40,50,700,63),(40,50,340,90),(40,50,340,50)])
def test_implausible_skew_fit_remains_unchanged(actual):
    shape=text_shape(2);before=shape._element.xml
    assert not fit_local(shape,(40,50,340,62.5),actual)
    assert shape._element.xml==before


@pytest.mark.parametrize('desired_height,actual_height',[(1,1.5),(.1,.2),(.2,.1)])
def test_pixel_noise_does_not_bypass_relative_height_guard(desired_height,actual_height):
    shape=text_shape(2);before=shape._element.xml
    assert not fit_local(shape,(40,50,340,50+desired_height),(40,50,340,50+actual_height))
    assert shape._element.xml==before


@pytest.mark.parametrize('width,desired_height,actual_height',[(310,1.9,2.3),(250,2.2,1.9)])
def test_pixel_noise_does_not_bypass_original_width_guard(width,desired_height,actual_height):
    shape=text_shape(2);before=shape._element.xml
    assert not fit_local(shape,(40,50,40+width,50+desired_height),(40,50,340,50+actual_height))
    assert shape._element.xml==before


@pytest.mark.parametrize('text,width,desired_height,actual_height',[
    ('中'*40,237,12.5,13),
    ('中'*21,360,13,12.5),
])
def test_unusable_stable_height_keeps_feasible_optical_fit(text,width,desired_height,actual_height):
    shape=text_shape(2);shape.text_frame.paragraphs[0].runs[0].text=text
    assert fit_local(shape,(40,50,40+width,50+desired_height),(40,50,340,50+actual_height))
    assert shape.text_frame.paragraphs[0].runs[0].font.size.pt==pytest.approx(12.5*desired_height/actual_height,abs=.011)


@pytest.mark.parametrize('angle',[2,358,88,92,178,182,268,272])
def test_initial_skew_fit_establishes_optical_size_before_stabilizing(angle):
    shape=text_shape(angle)
    assert fit_local(shape,(40,50,340,62.5),(40,50,340,63),stabilize=False)
    assert shape.text_frame.paragraphs[0].runs[0].font.size.pt==pytest.approx(12.5*12.5/13,abs=.011)


@pytest.mark.parametrize('requested,expected',[(None,1.5),(.75,.75),(2,1.5)])
def test_skew_refinement_reserves_rendering_margin_without_relaxing_tight_targets(requested,expected):
    from smartppt.ocr_fit import refinement_tolerance
    row={} if requested is None else {'refinement_tolerance_points':requested}
    assert refinement_tolerance(text_shape(358),row)==expected


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_quarter_turn_refinement_keeps_existing_requested_tolerance(angle):
    from smartppt.ocr_fit import refinement_tolerance
    shape=text_shape(angle)
    assert refinement_tolerance(shape,{})==2
    assert refinement_tolerance(shape,{'refinement_tolerance_points':.75})==.75
    assert refinement_tolerance(shape,{'refinement_tolerance_points':3})==3
