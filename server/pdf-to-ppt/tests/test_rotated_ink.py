from contextlib import contextmanager
from PIL import Image,ImageDraw
from pptx import Presentation
from pptx.util import Pt
import pytest
from smartppt.layout import add_text
from smartppt.ocr_fit import raster_bounds

@pytest.mark.parametrize('angle,bbox',[(90,[20,50,35,550]),(270,[365,50,380,550]),(0,[25,10,375,25]),(180,[25,575,375,590])])
def test_long_rotated_line_near_page_edge_is_measured_without_canvas_clipping(angle,bbox):
 image=Image.new('RGB',(800,1200),'white');l,t,r,b=bbox;ImageDraw.Draw(image).rectangle((l*2,t*2,r*2-1,b*2-1),fill='black')
 class Page:
  def get_size(self):return 400,600
  def render(self,scale):
   class Bitmap:
    def to_pil(self):return image.copy()
    def close(self):pass
   return Bitmap()
 p=Presentation();s=p.slides.add_slide(p.slide_layouts[6]);cx,cy=(l+r)/2,(t+b)/2
 width,height=(b-t,r-l) if angle in (90,270) else (r-l,b-t)
 shape=add_text(s,'Measured text 123',cx-width/2,cy-height/2,width,height,15);shape.rotation=angle
 target={'shape':0,'bbox':bbox,'quad':[(l,t),(r,t),(r,b),(l,b)]}
 result=raster_bounds(Page(),s,[target],{0:bbox})
 assert 0 in result
 assert max(abs(a-b) for a,b in zip(*result[0]))<=.5
