"""Known-font tracking fixtures and conservative reranking boundaries."""
import os
import numpy as np
import pytest
from PIL import Image, ImageChops, ImageDraw, ImageFont
from smartppt.cjk_font import cjk_font
from smartppt.cjk_glyphs import GlyphEvidence, rerank


@pytest.mark.parametrize('family,key,weight', [
    ('Noto Sans SC', 'SMARTPPT_CJK_FONT', 100),
    ('Noto Sans SC', 'SMARTPPT_CJK_FONT', 400),
    ('Noto Sans SC', 'SMARTPPT_CJK_FONT', 700),
    ('Noto Serif SC', 'SMARTPPT_CJK_SERIF_FONT', 200),
    ('Noto Serif SC', 'SMARTPPT_CJK_SERIF_FONT', 400),
    ('Noto Serif SC', 'SMARTPPT_CJK_SERIF_FONT', 700),
])
@pytest.mark.parametrize('size', [20, 40])
@pytest.mark.parametrize('tracking', [0, 2, 5])
@pytest.mark.parametrize('dark', [False, True])
def test_known_font_tracking_does_not_regress(family, key, weight, size, tracking, dark, monkeypatch):
    if not all(os.getenv(k) for k in ['SMARTPPT_CJK_FONT', 'SMARTPPT_CJK_SERIF_FONT']):
        pytest.skip('optional pinned CJK fonts required')
    font = ImageFont.truetype(os.environ[key], size)
    font.set_variation_by_axes([weight])
    background, foreground = ((24, 36, 48), (240, 228, 216)) if dark else ((255, 255, 255), (0, 0, 0))
    text = '本月营业收入增长利润情况'
    image = Image.new('RGB', (1500, 100), background)
    draw = ImageDraw.Draw(image)
    x = 5
    for char in text:
        draw.text((x, 5), char, font=font, fill=foreground)
        x += font.getlength(char) + tracking
    image = image.crop(ImageChops.difference(image, Image.new('RGB', image.size, background)).getbbox())
    with monkeypatch.context() as patch:
        patch.setattr('smartppt.cjk_glyphs.rerank', lambda text, ink, choices, fonts: choices[0])
        baseline = cjk_font(text, image, background)
    choice = cjk_font(text, image, background)
    expected_family = 'SmartPDF Sans100' if weight == 100 else 'SmartPDF Serif200' if weight == 200 else family
    expected = expected_family, weight
    previous = baseline['family'], baseline['weight']
    actual = choice['family'], choice['weight']
    if previous == expected:
        assert actual == expected
    if actual != previous:
        assert actual == expected
        assert choice['error'] <= .30
        assert choice['matched'] == (choice['error'] <= .20)
    if size == 40 or (tracking <= 2 and (family == 'Noto Sans SC' and weight == 400 or weight == 700)):
        assert actual == expected
    if family == 'Noto Sans SC' and weight == 400 and size == 20 and tracking == 5:
        assert actual == previous  # Wider tracking can fail final Office fitting.
    if family == 'Noto Serif SC' and weight == 400 and size == 40 and tracking == 5:
        assert previous != expected
        assert choice['glyph_error'] < .18


@pytest.mark.parametrize('text,shape', [
    ('中文', (20, 50)), ('中文混排12', (20, 200)), ('中文 含空格', (20, 200)),
    ('中文标点。', (20, 200)), ('字' * 65, (20, 2000)), ('中文字体', (7, 100)),
    ('中文字体', (257, 100)), ('中文字体', (20, 4097)),
])
def test_unsupported_geometry_and_text_have_no_glyph_score(text, shape):
    evidence = GlyphEvidence(text, np.zeros(shape))
    assert evidence.score(None) is None


def test_connected_ink_is_not_split_into_fictitious_glyphs():
    evidence = GlyphEvidence('中文字体', np.ones((20, 80)))
    assert evidence.score(None) is None


@pytest.mark.parametrize('winner_error,scores', [
    (.31, [(0.3, .3), (.1, .2)]),  # Original whole-line admission gate still applies.
    (.25, [(0.21, .3), (.19, .2)]),  # Absolute glyph evidence is weak.
    (.25, [(0.12, .2), (.10, .2)]),  # Ambiguous family/weight margin.
    (.25, [(0.3, .3), (.10, .31)]),  # One inconsistent glyph / mixed style.
    (.25, [None, (.10, .2)]),  # Baseline could not be compared reliably.
])
def test_uncertain_ranking_preserves_baseline(winner_error, scores, monkeypatch):
    baseline = {'error': .2, 'path': 'a', 'weight': 400}
    alternative = {'error': winner_error, 'path': 'b', 'weight': 700}
    scores = iter(scores)
    monkeypatch.setattr(GlyphEvidence, 'score', lambda self, font: next(scores))
    assert rerank('中文字体', np.ones((20, 80)), [baseline, alternative],
                  {('a', 400): None, ('b', 700): None}) is baseline
