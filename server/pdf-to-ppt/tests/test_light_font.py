"""Pinned Light derivative changes identity, never source outlines or rights."""
import os
from pathlib import Path
from io import BytesIO
from hashlib import sha256
from collections import defaultdict
import pytest
from fontTools.ttLib import TTFont
from smartppt import light_font as light
from smartppt.config import ConversionError

@pytest.fixture
def approved(monkeypatch):
    root=os.getenv('SMARTPPT_CMU_FONT_DIR')
    if not root:pytest.skip('pinned CMU 0.7.0 inputs required')
    path=Path(root)/light.FILENAME
    if not path.is_file():pytest.skip('pinned CMU Light input required')
    data=path.read_bytes();assert len(data)==light.SIZE and sha256(data).hexdigest()==light.SHA256
    monkeypatch.setenv('SMARTPPT_CMU_FONT_DIR',str(path.parent));return data


def test_missing_optional_font_fails_closed(monkeypatch,tmp_path):
    monkeypatch.delenv('SMARTPPT_CMU_FONT_DIR',raising=False)
    assert not light.capability()
    with pytest.raises(ConversionError,match='missing'):light.ttf_bytes()
    monkeypatch.setenv('SMARTPPT_CMU_FONT_DIR',str(tmp_path))
    assert not light.capability('Review')
    with pytest.raises(ConversionError,match='missing'):light.approved_cmap()

@pytest.mark.parametrize('style',['bold','italic','boldItalic','Light','',None])
def test_unsupported_styles_never_synthesized(style):
    with pytest.raises(ConversionError,match='style_unsupported'):light.ttf_bytes(style)

@pytest.mark.parametrize('bold,italic',[(True,False),(False,True),(True,True)])
def test_optional_capability_rejects_other_styles(bold,italic):
    assert not light.capability('Review',bold=bold,italic=italic)

@pytest.mark.parametrize('kind',['short','long','same_size_tamper','directory'])
def test_bad_source_rejected(approved,tmp_path,monkeypatch,kind):
    path=tmp_path/light.FILENAME
    if kind=='directory':path.mkdir()
    else:path.write_bytes({'short':approved[:-1],'long':approved+b'0','same_size_tamper':b'0'+approved[1:]}[kind])
    monkeypatch.setenv('SMARTPPT_CMU_FONT_DIR',str(tmp_path))
    assert not light.capability()
    with pytest.raises(ConversionError,match='missing|integrity_failed'):light.ttf_bytes()


def test_cached_conversion_does_not_hide_source_tamper(approved,tmp_path,monkeypatch):
    path=tmp_path/light.FILENAME;path.write_bytes(approved)
    monkeypatch.setenv('SMARTPPT_CMU_FONT_DIR',str(tmp_path))
    assert light.ttf_bytes()
    path.write_bytes(b'0'+approved[1:])
    with pytest.raises(ConversionError,match='integrity_failed'):light.ttf_bytes()
    with pytest.raises(ConversionError,match='integrity_failed'):light.convert_font(b'0'+approved[1:])


def test_deterministic_and_table_change_boundary(approved,monkeypatch):
    import fontTools.ttLib.tables._h_e_a_d as head
    outputs=[]
    for stamp in (3000000000,4000000000):
        monkeypatch.setattr(head,'timestampNow',lambda value=stamp:value)
        light.convert_font.cache_clear();outputs.append(light.ttf_bytes())
    assert outputs[0]==outputs[1]
    with TTFont(BytesIO(approved)) as before,TTFont(BytesIO(outputs[0])) as after:
        assert set(before.reader.keys())==set(after.reader.keys())
        for tag in before.reader.keys():
            if tag not in ('head','name'):assert before.reader[tag]==after.reader[tag],tag
        # head only changes its whole-file checksum, not font timestamps,
        # dimensions, flags, format or revision.
        a,b=before.reader['head'],after.reader['head']
        assert a[:8]+a[12:]==b[:8]+b[12:]
        assert before.getGlyphOrder()==after.getGlyphOrder()
        assert before['hmtx'].metrics==after['hmtx'].metrics
        assert before.getBestCmap()==after.getBestCmap()
        assert after['OS/2'].fsType==0 and after['OS/2'].usWeightClass==200
        assert after['post'].isFixedPitch==0


def test_full_naming_and_license_retained(approved):
    with TTFont(BytesIO(approved)) as before,TTFont(BytesIO(light.ttf_bytes())) as after:
        assert before['name'].getDebugName(0)==after['name'].getDebugName(0)
        for ident in (1,16,21):assert after['name'].getDebugName(ident)==light.FAMILY
        for ident in (2,17,22):assert after['name'].getDebugName(ident)=='Regular'
        for ident in (3,4,6,18,20,25):
            assert 'SmartPDF' in after['name'].getDebugName(ident)
        for n in after['name'].names:
            if n.nameID in (1,2,3,4,6,16,17,18,20,21,22,25):
                assert 'Computer Modern Unicode fonts' not in n.toUnicode()
                assert n.toUnicode() not in {'CMU Typewriter Text','CMUTypewriter-Light','Light'}
        license_text=Path(light.__file__).with_name('OFL-CMU.txt').read_text()
        assert license_text in after['name'].getDebugName(13)
        assert light.NOTICE in after['name'].getDebugName(13)


def test_cmap_aliases_and_raw_plus_nfkc_capability(approved):
    with TTFont(BytesIO(approved)) as font:
        mapping=font.getBestCmap();aliases=defaultdict(list)
        for code,glyph in mapping.items():aliases[glyph].append(code)
        # This exact approved font has no ambiguous reverse Unicode aliases;
        # no glyph duplication or layout-table modification is needed.
        assert all(len(codes)==1 for codes in aliases.values())
    assert light.approved_cmap()==frozenset(mapping)
    assert light.capability('Review 123.45 noam@example.com')
    assert not light.capability('\U0010ffff')
    assert not light.capability('\uff21') # NFKC ASCII must not hide missing raw glyph.
    assert not light.capability('\n')


def test_embedding_and_renderer_use_same_complete_ttf(approved,tmp_path):
    import struct,zipfile
    from pptx import Presentation
    from smartppt.layout import add_text
    from smartppt.font_embedding import bundled_payloads,embed_noto
    from smartppt.render_fonts import materialize_variant_fonts
    prs=Presentation();slide=prs.slides.add_slide(prs.slide_layouts[6])
    add_text(slide,'Review 123.45',30,30,400,40,18,light.FAMILY)
    before=tmp_path/'before.pptx';after=tmp_path/'after.pptx';prs.save(before)
    payloads=bundled_payloads(family=light.FAMILY)
    assert set(payloads)=={'regular'}
    payload=payloads['regular'];size=struct.unpack_from('<I',payload,4)[0]
    assert payload[-size:]==light.ttf_bytes()
    assert struct.unpack_from('<H',payload,32)[0]==0
    embed_noto(before,after,payloads,light.FAMILY)
    with zipfile.ZipFile(after) as package:
        assert [package.read(n) for n in package.namelist() if n.endswith('.fntdata')]==[payload]
    directory=materialize_variant_fonts([after],tmp_path)
    assert [p.read_bytes() for p in directory.glob('*.ttf')]==[light.ttf_bytes()]
    for args in ({'bold':True},{'styles':{'regular','italic'}},{'styles':{'boldItalic'}}):
        with pytest.raises(ConversionError,match='style_unsupported'):bundled_payloads(family=light.FAMILY,**args)


@pytest.mark.skipif(not os.getenv('SMARTPPT_TEST_RENDERER'),reason='real Office renderer required')
def test_actual_light_identity_before_and_after_embedding(approved,tmp_path):
    from contextlib import closing
    import pypdfium2 as pdfium
    from pptx import Presentation
    from smartppt.layout import add_text
    from smartppt.font_embedding import bundled_payloads,embed_noto
    from smartppt.render_gate import render_presentations
    from smartppt.config import Settings
    text='Light 123.45 noam@example.com'
    prs=Presentation();slide=prs.slides.add_slide(prs.slide_layouts[6])
    add_text(slide,text,30,30,600,40,18,light.FAMILY)
    before=tmp_path/'before.pptx';after=tmp_path/'after.pptx';prs.save(before)
    embed_noto(before,after,bundled_payloads(family=light.FAMILY),light.FAMILY)
    rendered=render_presentations([before,after],tmp_path,Settings(renderer_path=os.environ['SMARTPPT_TEST_RENDERER']))
    pixels=[]
    for file in rendered:
        with pdfium.PdfDocument(file) as doc,closing(doc[0]) as page,closing(page.get_textpage()) as tp:
            raw=''.join(chr(pdfium.raw.FPDFText_GetUnicode(tp,i)) for i in range(tp.count_chars()))
            assert raw.count(text)==1
            start=raw.index(text)
            for i,c in enumerate(text,start):
                if c.isspace():continue
                obj=tp.get_textobj(i);assert obj is not None
                assert obj.get_font().get_base_name().split('+')[-1]=='SmartPDFCMUTypewriterLight-Regular'
            with closing(page.render(scale=3)) as bitmap:pixels.append(bitmap.to_pil().tobytes())
    assert pixels[0]==pixels[1]
