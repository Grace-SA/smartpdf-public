import os
from pathlib import Path
import pytest
from pptx import Presentation
from pptx.util import Pt
from smartppt.layout import add_text
from smartppt.config import Settings
from smartppt.portable_fonts import try_portable_fonts,split_script_shapes
from smartppt.quality import normalized,shape_text
from smartppt.render_gate import render_presentations

@pytest.mark.skipif(not os.getenv('SMARTPPT_TEST_RENDERER') or not os.getenv('SMARTPPT_CJK_FONT'),reason='pinned CJK font and real Office renderer required')
@pytest.mark.parametrize('angle',[90,270,2,358])
def test_rotated_cjk_segments_remain_on_page_and_keep_complete_numbers(tmp_path,angle):
 settings=Settings(renderer_path=os.environ['SMARTPPT_TEST_RENDERER'])
 target=tmp_path/'original.pptx';p=Presentation();p.slide_width=Pt(500);p.slide_height=Pt(500);slide=p.slides.add_slide(p.slide_layouts[6]);text='中文预算123.45元，年度2026。'
 shape=add_text(slide,text,100,200,300,40,16,'Noto Sans SC');shape.rotation=angle;p.save(target)
 source=render_presentations([target],tmp_path,settings)[0]
 isolated=Presentation(target);targets=split_script_shapes(isolated,source)
 assert targets and len(targets[0])>1
 for row in targets[0]:
  l,t,r,b=row['bbox'];assert 0<=l<r<=500 and 0<=t<b<=500
 assert normalized(''.join(shape_text(isolated.slides[0].shapes)))==normalized(text)
 report={'pages':[{'page':1,'route':'paddle-ocr'}]};try_portable_fonts(source,target,report,settings)
 assert report['font_portability']['validated'],report
 result=Presentation(target);texts=list(shape_text(result.slides[0].shapes));assert normalized(''.join(texts))==normalized(text)
 assert any('123.45' in t for t in texts)
 if report['font_portability']['positioned_script_pages']:
  assert len(texts)>1
 else:
  # Splitting must never bypass the independent visual guard, even when a
  # renderer-perfect baseline leaves no room for added antialiasing differences.
  assert report['font_portability']['script_layout_rejected_pages']==[1]
  assert texts==[text]
 for shape in result.slides[0].shapes:
  if shape.has_text_frame:
   assert shape.rotation==pytest.approx(angle,abs=.01)
   assert 0<shape.left/Pt(1)<500 and 0<shape.top/Pt(1)<500
