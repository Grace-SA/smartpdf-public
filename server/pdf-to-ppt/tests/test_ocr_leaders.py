"""Synthetic pixels only: retain recognized punctuation and all guide ink."""
from copy import deepcopy
import numpy as np
import pytest
from smartppt.consensus import erase_bounds
from smartppt.ocr_leaders import trim_dot_leaders


def sample(text="目录标题", right=101, dots=12):
    image = np.full((70,260,3),255,dtype=np.uint8)
    for x in (15,35,55,75):
        image[20:40,x:x+12] = 0
    for x in range(94,94+dots*10,10):
        image[35:38,x:x+3] = 0
    line = {"text":text,"confidence":.99,
            "polygon":[[10,15],[right,15],[right,44],[10,44]]}
    return image,[line]


@pytest.mark.parametrize("text,right,expected", [("目录标题",101,90),("目录标题.",111,100)])
def test_trim_only_unrecognized_guides_preserves_text_and_source(text,right,expected):
    image,lines = sample(text,right)
    original = deepcopy(lines); pixels = image.copy()
    refined,changed,ambiguous,verified = trim_dot_leaders(image,lines)
    assert changed == verified == [0] and ambiguous == []
    assert lines == original and np.array_equal(image,pixels)
    assert refined[0]["text"] == text and refined[0]["confidence"] == .99
    l,t,r,b = erase_bounds(refined[0])
    assert abs(r-expected)<=2
    cleared = image.copy();cleared[t:b,l:r]=255
    first_preserved = 104 if text.endswith(".") else 94
    assert np.array_equal(cleared[:,first_preserved:],image[:,first_preserved:])
    assert np.all(cleared[20:40,75:87] == 255)
    if text.endswith("."):assert np.all(cleared[35:38,94:97] == 255)


@pytest.mark.parametrize("text", ["目录标题7","目录标题3.14","目录标题...","目录标题。","Title","目录标A","标题"])
def test_no_inferred_punctuation_or_numbers(text):
    image,lines = sample(text)
    assert trim_dot_leaders(image,lines) == (lines,[],[],[])


@pytest.mark.parametrize("kind", ["short","skew","dark","irregular","vertical","outside"])
def test_unproven_guide_never_changes_geometry(kind):
    image,lines = sample(dots=5 if kind=="short" else 12)
    if kind=="skew":lines[0]["polygon"][1][1]+=1
    if kind=="dark":image=255-image
    if kind=="irregular":
        image[:,94:]=255
        for x in (94,104,119,136,145,165,174,194,205):image[35:38,x:x+3]=0
    if kind=="vertical":lines[0]["polygon"][1][0]=lines[0]["polygon"][2][0]=20
    if kind=="outside":lines[0]["polygon"][0][0]=lines[0]["polygon"][3][0]=-2
    assert trim_dot_leaders(image,lines) == (lines,[],[],[])


def test_no_blank_cut_keeps_proven_intrusion_ambiguous():
    image,lines = sample()
    image[15:45,87:94]=230
    refined,changed,ambiguous,verified=trim_dot_leaders(image,lines)
    assert refined==lines and changed==verified==[] and ambiguous==[0]


@pytest.mark.parametrize("text", ["目录标题","目录标题."])
@pytest.mark.parametrize("thin", [False,True])
def test_faint_first_dot_cannot_be_skipped_or_erased(text,thin):
    image,lines=sample(text,right=111)
    image[35:38,94:97]=255
    image[35:36 if thin else 38,94:97]=230
    refined,changed,ambiguous,verified=trim_dot_leaders(image,lines)
    assert refined==lines and changed==verified==[] and ambiguous==[0]


@pytest.mark.parametrize("ambiguous", [False,True])
def test_slide_background_preserves_guide_or_entire_ambiguous_line(tmp_path,monkeypatch,ambiguous):
    import hashlib
    from io import BytesIO
    from PIL import Image
    from pptx import Presentation
    from pptx.util import Pt
    from smartppt.assisted import ocr_slide
    image,lines=sample()
    if ambiguous:image[15:45,87:94]=230
    path=tmp_path/'synthetic.png';Image.fromarray(image).save(path)
    record={'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'image_size':[260,70],'lines':lines}
    before=deepcopy(record)
    monkeypatch.setattr('smartppt.assisted.latin_font',lambda *args:None)
    monkeypatch.setenv('SMARTPPT_CJK_FONT',str(tmp_path/'absent.ttf'))
    prs=Presentation();prs.slide_width=Pt(520);prs.slide_height=Pt(140)
    slide=prs.slides.add_slide(prs.slide_layouts[6])
    class Page:
        def get_size(self):return 260,70
    result=ocr_slide(prs,slide,Page(),path,record,line_approvals=[True])
    with Image.open(BytesIO(slide.shapes[0].image.blob)) as background:
        pixels=np.asarray(background)
    assert record==before
    if ambiguous:
        assert result['editable_lines']==0 and np.array_equal(pixels,image)
        assert 'ambiguous_dot_leader_kept_as_image' in result['warnings']
    else:
        assert result['editable_lines']==1 and slide.shapes[1].text==lines[0]['text']
        assert np.array_equal(pixels[:,94:],image[:,94:])
        assert np.all(pixels[20:40,75:87]==255)
        assert result['ink_targets'][0]['refinement_tolerance_points']==1
