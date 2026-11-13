"""Pinned base-font provenance and exact render/embedding payload regressions."""
from contextlib import closing
from hashlib import sha256
from io import BytesIO
import os
from pathlib import Path
import struct
from types import SimpleNamespace
import zipfile

from fontTools.ttLib import TTFont
import pypdfium2 as pdfium
from pptx import Presentation
import pytest

from smartppt import base_font as base
from smartppt.config import ConversionError, Settings
from smartppt.font_embedding import bundled_payloads, embed_noto
from smartppt.layout import add_text
from smartppt.render_fonts import materialize_variant_fonts
from smartppt.render_gate import render_presentations
from smartppt.quality import normalized


@pytest.fixture(autouse=True)
def clean_caches():
    for fn in (base.builtin_data, base.approved_cmap, base.ttf_bytes): fn.cache_clear()
    yield
    for fn in (base.builtin_data, base.approved_cmap, base.ttf_bytes): fn.cache_clear()


def test_builtin_provenance_and_deterministic_full_font():
    assert len(base.builtin_data()) == base.SOURCE_BYTES
    assert sha256(base.builtin_data()).hexdigest() == base.SOURCE_SHA256
    a = base.ttf_bytes()
    for fn in (base.builtin_data, base.approved_cmap, base.ttf_bytes): fn.cache_clear()
    assert base.ttf_bytes() == a
    with TTFont(BytesIO(a)) as font:
        assert font['name'].getDebugName(1) == base.FAMILY
        assert font['OS/2'].fsType == 0
        assert font['head'].created == font['head'].modified == 2082844800
        assert 'Foxit Software' in font['name'].getDebugName(13)
        assert 'Redistribution and use' in font['name'].getDebugName(13)
        assert set(font.getBestCmap()) == set(base.approved_cmap())
        assert set(map(ord, 'Revenue -123.45% café')) <= set(font.getBestCmap())


def test_tampered_builtin_hash_fails_closed(monkeypatch):
    monkeypatch.setattr(base, 'SOURCE_SHA256', '0' * 64)
    with pytest.raises(ConversionError, match='portable_base_font_integrity_failed'):
        base.ttf_bytes()


@pytest.mark.parametrize('name,embedded,bold,italic,text', [
    ('Helvetica', 1, False, False, '123.45'),
    ('Helvetica', 0, True, False, '123.45'),
    ('Helvetica', 0, False, True, '123.45'),
    ('Helvetica-Bold', 0, False, False, '123.45'),
    ('ABCDEF+Helvetica', 0, False, False, '123.45'),
    ('Arial', 0, False, False, '123.45'),
    ('Helvetica', 0, False, False, '中文'),
    ('Helvetica', 0, False, False, 'e\u0301'),
])
def test_unsupported_source_fonts_and_characters_stay_on_existing_route(monkeypatch, name, embedded, bold, italic, text):
    data = base.builtin_data()
    monkeypatch.setattr(base.pdfium.raw, 'FPDFFont_GetIsEmbedded', lambda _: embedded)
    monkeypatch.setattr(base, 'font_data', lambda _: data)
    font = SimpleNamespace(get_base_name=lambda: name)
    assert base.source_family(font, text, bold=bold, italic=italic) is None


def test_same_name_with_wrong_font_bytes_is_rejected(monkeypatch):
    monkeypatch.setattr(base.pdfium.raw, 'FPDFFont_GetIsEmbedded', lambda _: 0)
    monkeypatch.setattr(base, 'font_data', lambda _: None)
    assert base.source_family(SimpleNamespace(get_base_name=lambda: 'Helvetica'), '123') is None


@pytest.mark.parametrize('kwargs', [{'bold': True}, {'styles': {'italic'}}, {'styles': {'boldItalic'}}, {'styles': {'unknown'}}])
def test_unsupported_output_styles_cannot_embed(kwargs):
    with pytest.raises(ConversionError, match='portable_base_font_style_unsupported'):
        bundled_payloads(family=base.FAMILY, **kwargs)


def test_renderer_and_eot_use_identical_approved_bytes(tmp_path):
    data = base.ttf_bytes(); payloads = bundled_payloads(family=base.FAMILY)
    payload = payloads['regular']; total, size, version, flags = struct.unpack_from('<IIII', payload)
    assert total == len(payload) and size == len(data) and version == 0x20001 and flags == 0
    assert payload[-size:] == data
    prs = Presentation(); slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_text(slide, 'Budget 123.45', 30, 40, 300, 30, 18, base.FAMILY)
    before = tmp_path / 'before.pptx'; after = tmp_path / 'embedded.pptx'; prs.save(before)
    embed_noto(before, after, payloads, base.FAMILY)
    with zipfile.ZipFile(after) as package:
        fonts = [name for name in package.namelist() if name.endswith('.fntdata')]
        assert len(fonts) == 1 and package.read(fonts[0]) == payload
    directory = materialize_variant_fonts([after], tmp_path)
    assert [p.read_bytes() for p in directory.glob('*.ttf')] == [data]


@pytest.mark.skipif(not os.getenv('SMARTPPT_TEST_RENDERER'), reason='real Office renderer required')
def test_real_render_after_embedding_uses_approved_family_and_text(tmp_path):
    prs = Presentation(); slide = prs.slides.add_slide(prs.slide_layouts[6])
    text = 'Region 123.45 Footer 999 café'
    add_text(slide, text, 30, 40, 600, 30, 18, base.FAMILY)
    before = tmp_path / 'before.pptx'; after = tmp_path / 'embedded.pptx'; prs.save(before)
    embed_noto(before, after, bundled_payloads(family=base.FAMILY), base.FAMILY)
    results = render_presentations([before, after], tmp_path, Settings(renderer_path=os.environ['SMARTPPT_TEST_RENDERER']))
    for result in results:
        with pdfium.PdfDocument(result) as doc, closing(doc[0]) as page, closing(page.get_textpage()) as tp:
            assert normalized(tp.get_text_range()) == normalized(text)
            names = [o.get_font().get_base_name() for o in page.get_objects(filter=[pdfium.raw.FPDF_PAGEOBJ_TEXT])]
            assert names and all('SmartPDFBaseSans' in name for name in names), names


def test_real_unembedded_helvetica_selects_pinned_family():
    from reportlab.pdfgen import canvas
    stream = BytesIO(); c = canvas.Canvas(stream); c.setFont('Helvetica', 14)
    c.drawString(30, 700, 'Revenue 123.45'); c.save()
    with pdfium.PdfDocument(stream.getvalue()) as doc, closing(doc[0]) as page:
        fonts = [o.get_font() for o in page.get_objects(filter=[pdfium.raw.FPDF_PAGEOBJ_TEXT])]
        assert fonts and all(base.source_family(font, 'Revenue 123.45') == base.FAMILY for font in fonts)


def test_license_is_in_declared_wheel_package_data():
    import tomllib
    config = tomllib.loads((Path(__file__).parents[1] / 'pyproject.toml').read_text())
    assert 'BSD-PDFium-base-font.txt' in config['tool']['setuptools']['package-data']['smartppt']
    license_text = Path(base.__file__).with_name('BSD-PDFium-base-font.txt').read_text()
    assert 'Foxit Software' in license_text and 'PDFium Authors' in license_text
