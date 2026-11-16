from pathlib import Path
import sys
import pytest
from pptx import Presentation
from smartppt.config import Settings,ConversionError
from smartppt.render_gate import render_presentations

def test_renderer_success_without_output_cannot_reuse_previous_pdf(tmp_path,monkeypatch):
 import smartppt.render_gate as module
 p=Presentation();p.slides.add_slide(p.slide_layouts[6]);source=tmp_path/'candidate.pptx';p.save(source)
 stale=tmp_path/'candidate.pdf';stale.write_bytes(b'%PDF-1.7 old geometry')
 monkeypatch.setattr(module.subprocess,'run',lambda *args,**kwargs:None)
 with pytest.raises(ConversionError,match='layout_render_failed'):
  render_presentations([source],tmp_path,Settings(renderer_path=sys.executable))
 assert not stale.exists()

def test_duplicate_render_names_cannot_share_geometry(tmp_path,monkeypatch):
 import smartppt.render_gate as module
 def forbidden(*args,**kwargs):raise AssertionError('Ambiguous render must not run')
 monkeypatch.setattr(module.subprocess,'run',forbidden)
 with pytest.raises(ConversionError,match='layout_render_name_collision'):
  render_presentations([tmp_path/'a/candidate.pptx',tmp_path/'b/candidate.pptx'],tmp_path,Settings(renderer_path=sys.executable))
