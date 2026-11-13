"""Explicit CM-Super names use reviewed CMU substitutes, not generic Arial."""
import pytest
from smartppt.layout import modern_face,font_style,font_family


@pytest.mark.parametrize('code,family,bold,italic',[
 ('rm','CMU Serif',False,False),('sl','CMU Serif',False,True),
 ('ti','CMU Serif',False,True),('bx','CMU Serif',True,False),
 ('bl','CMU Serif',True,True),('bi','CMU Serif',True,True),
 ('rb','CMU Serif',True,False),('ss','CMU Sans Serif',False,False),
 ('si','CMU Sans Serif',False,True),('sx','CMU Sans Serif',True,False),
 ('so','CMU Sans Serif',True,True),('tt','CMU Typewriter Text',False,False),
 ('st','CMU Typewriter Text',False,True),('it','CMU Typewriter Text',False,True),
])
def test_explicit_cm_super_shape_codes(code,family,bold,italic):
 name='ABCDEF+SF'+code.upper()+'1000'
 assert modern_face(name)==family
 # Do not trust weight inferred from stems for a named regular face.
 assert font_style(name,900,0)==(bold,italic)


@pytest.mark.parametrize('name',['SFCC1000','SFTC1000','SFVT1000','SFVI1000','SFBMR10',
 'SFORm10','ISFLTT8','SFTT1000-Unknown','SFTT','SFTT1','SFTT10000','UnknownSFTT1000','CMMI10'])
def test_unknown_or_different_shapes_are_not_guessed(name):
 assert modern_face(name) is None


def test_alias_needs_operator_supplied_font_and_keeps_cjk_path(tmp_path,monkeypatch):
 monkeypatch.delenv('SMARTPPT_CMU_FONT_DIR',raising=False)
 assert font_family('Computer Modern','Budget 123',base_name='SFTT1000')[0]=='Arial'
 monkeypatch.setenv('SMARTPPT_CMU_FONT_DIR',str(tmp_path))
 assert font_family('Computer Modern','Budget 123',base_name='SFTT1000')[0]=='Arial'
 (tmp_path/'cmuntt.ttf').write_bytes(b'availability only; embedding checks pinned hash')
 assert font_family('Computer Modern','Budget 123',base_name='SFTT1000')==('CMU Typewriter Text',True)
 assert font_family('Computer Modern','预算123',base_name='SFTT1000')[0]=='Noto Sans SC'
