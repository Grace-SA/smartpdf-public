"""Approved CMU text must not silently render with a different installed font."""
import os,struct
from pathlib import Path
import pytest
from pptx import Presentation
from smartppt.layout import add_text
from smartppt.config import Settings,ConversionError
from smartppt.font_embedding import CMU_FACES,bundled_payloads,cmu_payload,noto_payload
from smartppt.render_fonts import materialize_variant_fonts


def deck(path,family):
 p=Presentation();s=p.slides.add_slide(p.slide_layouts[6]);add_text(s,'Review 123.45',10,10,300,30,16,family);p.save(path)


@pytest.mark.parametrize('family',list(CMU_FACES))
def test_cmu_used_family_requests_all_verified_faces(tmp_path,monkeypatch,family):
 import smartppt.render_fonts as fonts
 file=tmp_path/'source.pptx';deck(file,family);calls=[]
 def payloads(bold,name,styles):
  calls.append((bold,name,styles));return {style:struct.pack('<II',8+len(style),len(style))+style.encode() for style in styles}
 monkeypatch.setattr(fonts,'bundled_payloads',payloads)
 folder=materialize_variant_fonts([file,file],tmp_path)
 assert calls==[(False,family,{'regular','bold','italic','boldItalic'})]
 assert {p.read_bytes() for p in folder.glob('*.ttf')}=={s.encode() for s in ('regular','bold','italic','boldItalic')}


@pytest.mark.parametrize('kind',['missing','tampered'])
def test_missing_or_tampered_cmu_stops_before_office_render(tmp_path,monkeypatch,kind):
 from smartppt import render_gate
 file=tmp_path/'source.pptx';deck(file,'CMU Serif');fonts=tmp_path/'fonts';fonts.mkdir()
 monkeypatch.setenv('SMARTPPT_CMU_FONT_DIR',str(fonts))
 if kind=='tampered':(fonts/'cmunrm.ttf').write_bytes(b'unreviewed font bytes')
 monkeypatch.setattr(render_gate.subprocess,'run',lambda *a,**k:pytest.fail('must not render a substituted font'))
 with pytest.raises(ConversionError,match='portable_font_unavailable' if kind=='missing' else 'portable_font_integrity_failed'):
  render_gate.render_presentations([file],tmp_path,Settings(renderer_path='/bin/true'))
 assert not (tmp_path/'source.pdf').exists()


@pytest.mark.skipif(not os.getenv('SMARTPPT_CMU_FONT_DIR'),reason='pinned CMU inputs required')
def test_renderer_uses_exact_embedded_cmu_font_bytes(tmp_path):
 file=tmp_path/'source.pptx';deck(file,'CMU Sans Serif')
 folder=materialize_variant_fonts([file],tmp_path)
 payloads=bundled_payloads(False,'CMU Sans Serif',styles={'regular','bold','italic','boldItalic'})
 assert {p.read_bytes() for p in folder.glob('*.ttf')}=={p[-struct.unpack_from('<I',p,4)[0]:] for p in payloads.values()}


@pytest.mark.skipif(not os.getenv('SMARTPPT_CMU_FONT_DIR'),reason='pinned CMU inputs required')
def test_cmu_generation_is_independent_of_clock(monkeypatch):
 import fontTools.ttLib.tables._h_e_a_d as head
 data=(Path(os.environ['SMARTPPT_CMU_FONT_DIR'])/CMU_FACES['CMU Serif']['regular']['file']).read_bytes()
 outputs=[]
 for stamp in (3000000000,4000000000):
  monkeypatch.setattr(head,'timestampNow',lambda value=stamp:value);cmu_payload.cache_clear()
  outputs.append(cmu_payload(data,'CMU Serif','regular'))
 assert outputs[0]==outputs[1]
 cmu_payload.cache_clear()


@pytest.mark.skipif(not os.getenv('SMARTPPT_CJK_FONT'),reason='pinned Noto input required')
def test_noto_generation_is_independent_of_clock(monkeypatch):
 import fontTools.ttLib.tables._h_e_a_d as head
 data=Path(os.environ['SMARTPPT_CJK_FONT']).read_bytes();outputs=[]
 for stamp in (3000000000,4000000000):
  monkeypatch.setattr(head,'timestampNow',lambda value=stamp:value);noto_payload.cache_clear()
  outputs.append(noto_payload(data,family='SmartPDF Sans100'))
 assert outputs[0]==outputs[1]
 noto_payload.cache_clear()
