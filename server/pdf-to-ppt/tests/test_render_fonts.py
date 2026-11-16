import struct
from pptx import Presentation
from pptx.util import Pt
from smartppt.layout import add_text
from smartppt.render_fonts import materialize_variant_fonts

def test_only_used_font_attributes_request_approved_static_faces(tmp_path,monkeypatch):
 import smartppt.render_fonts as render
 p=Presentation();s=p.slides.add_slide(p.slide_layouts[6]);shape=add_text(s,'SmartPDF Sans100',10,10,200,25,14,'Arial');file=tmp_path/'test.pptx';p.save(file)
 def forbidden(*args):raise AssertionError('text content is not font provenance')
 monkeypatch.setattr(render,'bundled_payloads',forbidden)
 assert materialize_variant_fonts([file],tmp_path) is None
 assert not (tmp_path/'approved-static-fonts').exists()
 shape.text_frame.paragraphs[0].runs[0].font.name='SmartPDF Sans100';p.save(file);calls=[];data=b'exact approved static font bytes'
 def payloads(bold,family):
  calls.append((bold,family));return {'regular':struct.pack('<II',8+len(data),len(data))+data}
 monkeypatch.setattr(render,'bundled_payloads',payloads)
 directory=materialize_variant_fonts([file,file],tmp_path)
 assert calls==[(False,'SmartPDF Sans100')]
 fonts=list(directory.glob('*.ttf'));assert len(fonts)==1 and fonts[0].read_bytes()==data
 stamp=fonts[0].stat().st_mtime_ns;materialize_variant_fonts([file],tmp_path)
 assert fonts[0].stat().st_mtime_ns==stamp
