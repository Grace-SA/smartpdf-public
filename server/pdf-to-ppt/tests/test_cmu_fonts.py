import os,struct,zipfile
from io import BytesIO
from pathlib import Path
import pytest
from pptx import Presentation
from pptx.util import Pt
from fontTools.ttLib import TTFont
from smartppt.layout import font_family,font_style,cjk_text,add_text,graphical_font,modern_face
from smartppt.font_embedding import bundled_payloads,cmu_payload,CMU_FACES,P
from smartppt.config import Settings,ConversionError
from smartppt.portable_fonts import try_portable_fonts
from smartppt.render_gate import render_presentations
from smartppt.quality import normalized,shape_text
from lxml import etree as ET

@pytest.mark.parametrize('face,family,bold,italic',[
 ('ABCDEF+CMR10','CMU Serif',False,False),('CMBX12','CMU Serif',True,False),
 ('CMTI10','CMU Serif',False,True),
 ('CMSS10','CMU Sans Serif',False,False),('CMSSI10','CMU Sans Serif',False,True),
 ('CMSSBX10','CMU Sans Serif',True,False),('CMTT10','CMU Typewriter Text',False,False),
 ('CMUSerif-BoldItalic','CMU Serif',True,True),('CMUSansSerif-BoldOblique','CMU Sans Serif',True,True)])
def test_source_face_controls_modern_family_and_style(face,family,bold,italic,tmp_path,monkeypatch):
 for name in ("cmunrm.ttf","cmunss.ttf","cmuntt.ttf"):(tmp_path/name).write_bytes(b"availability only; embedding independently checks hashes")
 monkeypatch.setenv("SMARTPPT_CMU_FONT_DIR",str(tmp_path))
 assert font_family('Computer Modern','office ﬁ 123.45',base_name=face)[0]==family
 assert font_style(face,900)==(bold,italic)
 assert font_family('Unknown','中文',base_name=face)[0]=='Noto Sans SC'


@pytest.mark.parametrize('shape,family,bold,italic',[
 ('rm','CMU Serif',False,False),('sl','CMU Serif',False,True),
 ('ti','CMU Serif',False,True),('bx','CMU Serif',True,False),
 ('bl','CMU Serif',True,True),('bi','CMU Serif',True,True),
 ('rb','CMU Serif',True,False),('ss','CMU Sans Serif',False,False),
 ('si','CMU Sans Serif',False,True),('sx','CMU Sans Serif',True,False),
 ('so','CMU Sans Serif',True,True),('tt','CMU Typewriter Text',False,False),
 ('st','CMU Typewriter Text',False,True),('it','CMU Typewriter Text',False,True)])
@pytest.mark.parametrize('prefix,size',[('', '0900'),('ABCDEF+', '1000')])
def test_cm_super_known_shapes(shape,family,bold,italic,prefix,size,tmp_path,monkeypatch):
 face=prefix+'SF'+shape.upper()+size
 test_source_face_controls_modern_family_and_style(face,family,bold,italic,tmp_path,monkeypatch)
 # Explicit face names override contradictory PDF weight/italic estimates.
 assert font_style(face,100,64)==(bold,italic)


@pytest.mark.parametrize('face',['SFCC1000','SFSC1000','SFUI1000','SFVT1000','SFVI1000',
 'SFDH1000','SFRM10','SFRM1000Unknown','UnknownSFRM1000','SFBMR10','SFSSDC10','CMSY10'])
def test_cm_super_unknown_shapes_are_not_guessed(face):
 assert modern_face(face) is None


def test_cm_super_requires_available_family_file(tmp_path,monkeypatch):
 monkeypatch.setenv('SMARTPPT_CMU_FONT_DIR',str(tmp_path))
 assert font_family('Computer Modern','Budget 123',base_name='SFRM1000')[0]=='Arial'
 (tmp_path/'cmunss.ttf').write_bytes(b'availability only')
 assert font_family('Computer Modern','Budget 123',base_name='SFRM1000')[0]=='Arial'
 assert font_family('Computer Modern','Budget 123',base_name='SFSS1000')[0]=='CMU Sans Serif'

@pytest.mark.parametrize('text,expected',[('ﬁ ﬂ \ue000',False),('中文',True),('𠮷',True),('123.45',False)])
def test_chinese_detection_does_not_misclassify_latin_ligatures(text,expected):
 assert cjk_text(text)==expected


def test_unconfigured_modern_fonts_keep_existing_mapping(monkeypatch):
 monkeypatch.delenv('SMARTPPT_CMU_FONT_DIR',raising=False)
 assert font_family('Computer Modern','Budget 123',base_name='CMR10')[0]=='Arial'
 assert font_family('Times-Roman','office ﬁ')[0]=='Times New Roman'
 assert font_family('MathSymbols','123',base_name='CMSY10')[0]=='Arial'


def test_unapproved_static_font_never_embedded():
 with pytest.raises(ConversionError,match='portable_font_integrity_failed'):cmu_payload(b'unknown','CMU Serif','regular')

@pytest.mark.skipif(not os.getenv('SMARTPPT_CMU_FONT_DIR'),reason='optional pinned CMU fonts required')
@pytest.mark.parametrize('family',list(CMU_FACES))
def test_full_static_fonts_keep_all_faces_glyphs_and_license(family):
 payloads=bundled_payloads(True,family,{'italic','boldItalic'})
 assert set(payloads)=={'regular','bold','italic','boldItalic'}
 for style,data in payloads.items():
  total,size,version,flags=struct.unpack_from('<IIII',data)
  assert total==len(data) and version==0x20001 and flags==0
  with TTFont(BytesIO(data[-size:])) as font:
   assert font['OS/2'].fsType==0 and font['name'].getDebugName(1)==family
   assert 'Donald Ervin Knuth' in font['name'].getDebugName(13)
   assert 'PREAMBLE' in font['name'].getDebugName(13)
   assert set(map(ord,'Budget 123.45 αβγ'))<=set(font.getBestCmap())
   assert bool(font['OS/2'].fsSelection&1)==(style in ('italic','boldItalic'))


@pytest.mark.skipif(not os.getenv('SMARTPPT_CMU_FONT_DIR') or not os.getenv('SMARTPPT_TEST_RENDERER'),reason='optional pinned CMU fonts and real Office renderer required')
def test_real_multiple_families_and_italic_embedding_preserve_output(tmp_path):
 p=Presentation();p.slide_width=Pt(500);p.slide_height=Pt(400);s=p.slides.add_slide(p.slide_layouts[6])
 for i,(family,bold,italic) in enumerate([('CMU Serif',False,False),('CMU Serif',True,True),('CMU Sans Serif',False,True),('CMU Typewriter Text',True,False)]):
  add_text(s,'Scientific report αβγ 123.45',25,40+i*70,450,35,18,family,bold=bold,italic=italic)
 target=tmp_path/'source.pptx';p.save(target);settings=Settings(renderer_path=os.environ['SMARTPPT_TEST_RENDERER'])
 source=render_presentations([target],tmp_path,settings)[0];report={'pages':[{'page':1,'route':'native-coordinate'}]}
 try_portable_fonts(source,target,report,settings)
 assert report['font_portability']['embedded'],report
 assert report['font_portability']['families']=={'CMU Sans Serif':['regular','italic'],'CMU Serif':['regular','bold','boldItalic'],'CMU Typewriter Text':['regular','bold']}
 assert normalized(''.join(shape_text(Presentation(target).slides[0].shapes)))==normalized(''.join(shape_text(s.shapes)))
 with zipfile.ZipFile(target) as z:
  fonts=ET.fromstring(z.read('ppt/presentation.xml')).find('{'+P+'}embeddedFontLst')
  assert len(fonts)==3 and len([n for n in z.namelist() if n.endswith('.fntdata')])==7


@pytest.mark.parametrize("name",["CMMI10","ABCDEF+CMSY8","CMEX10","MSAM10","MSBM10","SymbolMT"])
def test_formula_fonts_are_explicitly_graphical(name):
 assert graphical_font(name)
 assert not graphical_font("CMR10")
