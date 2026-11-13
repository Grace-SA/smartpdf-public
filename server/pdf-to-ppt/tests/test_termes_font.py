"""Pinned optional Termes conversion must preserve rights, styles and glyph data."""
from contextlib import closing
from io import BytesIO
import os
from pathlib import Path
import struct
import zipfile
import pytest
from fontTools.ttLib import TTFont
import pypdfium2 as pdfium
from pptx import Presentation
from smartppt import termes_font as termes
from smartppt.config import ConversionError,Settings
from smartppt.font_embedding import bundled_payloads,embed_noto,eot_payload
from smartppt.layout import add_text,font_style
from smartppt.render_fonts import materialize_variant_fonts
from smartppt.render_gate import render_presentations


@pytest.fixture
def approved(monkeypatch):
 directory=os.getenv('SMARTPPT_TERMES_FONT_DIR')
 if not directory or not all((Path(directory)/v[0]).is_file() for v in termes.FACES.values()):
  pytest.skip('operator-supplied pinned TeX Gyre fonts required')
 termes.convert_font.cache_clear()
 yield Path(directory)
 termes.convert_font.cache_clear()


@pytest.mark.parametrize('style',termes.FACES)
def test_full_font_determinism_layout_metadata_and_rights(approved,style):
 raw=termes.approved_data(style);data=termes.ttf_bytes(style)
 termes.convert_font.cache_clear();assert termes.ttf_bytes(style)==data
 with TTFont(BytesIO(raw)) as original,TTFont(BytesIO(data)) as result:
  assert original.getGlyphOrder()==result.getGlyphOrder()
  assert original.getBestCmap()==result.getBestCmap()
  # Pinned faces have no alias glyphs to split for reliable text extraction.
  assert len(set(result.getBestCmap().values()))==len(result.getBestCmap())
  for tag in ('GPOS','GSUB','GDEF','hmtx'):
   if tag in original:assert original[tag].compile(original)==result[tag].compile(result)
  # Quadratic extrema rounding changes italic min right bearing by one unit.
  for key in ('ascent','descent','lineGap','advanceWidthMax','caretSlopeRise','caretSlopeRun','caretOffset'):
   assert getattr(result['hhea'],key)==getattr(original['hhea'],key)
  assert abs(result['hhea'].minRightSideBearing-original['hhea'].minRightSideBearing)<=1
  assert result['OS/2'].fsType==12
  assert result['OS/2'].fsSelection==original['OS/2'].fsSelection
  assert result['head'].macStyle==original['head'].macStyle
  assert result['head'].created==result['head'].modified==2082844800
  assert result['name'].getDebugName(0)==original['name'].getDebugName(0)
  assert result['name'].getDebugName(1)==termes.FAMILY
  assert 'LaTeX Project Public License' in result['name'].getDebugName(13)
  assert 'SmartPDF Termes derivative' in result['name'].getDebugName(13)
  assert 'GUST Font License' in result['name'].getDebugName(13)
  for attr in ('italicAngle','underlinePosition','underlineThickness','isFixedPitch'):
   assert getattr(result['post'],attr)==getattr(original['post'],attr)


@pytest.mark.parametrize('kind',['size','hash'])
def test_tamper_fails_even_after_cached_conversion(approved,tmp_path,monkeypatch,kind):
 raw=termes.approved_data('regular');termes.ttf_bytes('regular')
 damaged=raw+b'!' if kind=='size' else bytes([raw[0]^1])+raw[1:]
 (tmp_path/termes.FACES['regular'][0]).write_bytes(damaged)
 monkeypatch.setenv('SMARTPPT_TERMES_FONT_DIR',str(tmp_path))
 with pytest.raises(ConversionError,match='integrity_failed'):termes.ttf_bytes('regular')
 assert termes.source_family('NimbusRomNo9L-Regu') is None


@pytest.mark.parametrize('name,style',[
 ('ABCDEF+NimbusRomNo9L-Regu','regular'),('NimbusRomNo9L-Medi','bold'),
 ('NimbusRomNo9L-ReguItal','italic'),('NimbusRomNo9L-MediItal','boldItalic'),
 ('NimbusRoman-BoldItalic','boldItalic'),('TeXGyreTermes-Regular','regular')])
def test_explicit_face_selection(approved,name,style):
 assert termes.face_name(name)==style
 assert termes.source_family(name)==termes.FAMILY
 assert font_style(name,900)==(style in ('bold','boldItalic'),style in ('italic','boldItalic'))


@pytest.mark.parametrize('name',['Times-Roman','NimbusRoman-Unknown','NimbusRomNo9L-ReguFake','XNimbusRomNo9L-Regu','TeXGyreTermes','ABC+NimbusRomNo9L-Regu'])
def test_unknown_names_not_guessed(name):
 assert termes.face_name(name) is None
 assert termes.source_family(name) is None


def test_renderer_eot_and_style_bytes_identical(approved,tmp_path):
 payloads=bundled_payloads(family=termes.FAMILY,styles=set(termes.FACES))
 prs=Presentation();slide=prs.slides.add_slide(prs.slide_layouts[6])
 add_text(slide,'Termes 123',30,30,200,30,18,termes.FAMILY)
 source=tmp_path/'source.pptx';target=tmp_path/'embedded.pptx';prs.save(source)
 embed_noto(source,target,payloads,termes.FAMILY)
 with zipfile.ZipFile(target) as z:
  assert {z.read(n) for n in z.namelist() if n.endswith('.fntdata')}==set(payloads.values())
 directory=materialize_variant_fonts([target],tmp_path)
 assert {p.read_bytes() for p in directory.glob('*.ttf')}=={termes.ttf_bytes(s) for s in termes.FACES}
 for style,payload in payloads.items():
  data=termes.ttf_bytes(style);assert payload[-len(data):]==data
  assert struct.unpack_from('<H',payload,32)[0]==12
  with TTFont(BytesIO(data)) as f:
   with pytest.raises(ConversionError,match='not_installable'):eot_payload(f,data)
   assert eot_payload(f,data,editable_embedding=True)==payload


@pytest.mark.skipif(not os.getenv('SMARTPPT_TEST_RENDERER'),reason='real Office renderer required')
def test_actual_four_style_post_embedding_render(approved,tmp_path):
 prs=Presentation();slide=prs.slides.add_slide(prs.slide_layouts[6])
 for i,style in enumerate(termes.FACES):
  add_text(slide,'Style '+style+' 123.45',30,30+i*60,500,40,20,termes.FAMILY,bold=style in ('bold','boldItalic'),italic=style in ('italic','boldItalic'))
 before=tmp_path/'before.pptx';after=tmp_path/'after.pptx';prs.save(before)
 embed_noto(before,after,bundled_payloads(family=termes.FAMILY,styles=set(termes.FACES)),termes.FAMILY)
 rendered=render_presentations([after],tmp_path,Settings(renderer_path=os.environ['SMARTPPT_TEST_RENDERER']))[0]
 with pdfium.PdfDocument(rendered) as doc,closing(doc[0]) as page,closing(page.get_textpage()) as tp:
  text=tp.get_text_range()
  for style in termes.FACES:assert 'Style '+style+' 123.45' in text
  names={obj.get_font().get_base_name() for obj in page.get_objects() if obj.type==pdfium.raw.FPDF_PAGEOBJ_TEXT}
  for style in termes.FACES:assert any('SmartPDFTermes-'+style in n for n in names),names


def test_incomplete_optional_family_not_selected(approved,tmp_path,monkeypatch):
 (tmp_path/termes.FACES['regular'][0]).write_bytes(termes.approved_data('regular'))
 monkeypatch.setenv('SMARTPPT_TERMES_FONT_DIR',str(tmp_path))
 assert termes.source_family('NimbusRomNo9L-Regu') is None


def test_full_license_and_manifest_are_packaged():
 import tomllib
 config=tomllib.loads((Path(__file__).parents[1]/'pyproject.toml').read_text())
 package_data=config['tool']['setuptools']['package-data']['smartppt']
 for name in ('GFL-Termes.txt','LPPL-1.3c.txt','MANIFEST-SmartPDFTermes.txt'):
  assert name in package_data
  assert Path(termes.__file__).with_name(name).stat().st_size>500


def test_editable_opt_in_does_not_strip_other_embedding_restrictions(approved):
 with TTFont(BytesIO(termes.ttf_bytes('regular'))) as font:
  for flags in (2,4,6,10,0x100,0x200,0xffff):
   font['OS/2'].fsType=flags
   with pytest.raises(ConversionError,match='not_installable'):
    eot_payload(font,b'not used after license rejection',editable_embedding=True)
