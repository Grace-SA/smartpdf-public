import os
from io import BytesIO
import numpy as np
from PIL import Image
from pptx import Presentation
from pptx.util import Pt
from pypdf import PdfReader
import pytest
from smartppt.config import Settings
from smartppt.render_gate import render_presentations


@pytest.mark.skipif(not os.getenv('SMARTPPT_TEST_RENDERER'),reason='real Office renderer required')
def test_renderer_preserves_embedded_raster_pixels_without_jpeg_or_downsampling(tmp_path):
 y,x=np.mgrid[:600,:800]
 pixels=np.stack(((x//3+y//7)%256,(x//5+y//2)%256,(x//9+y//11)%256),axis=2).astype(np.uint8)
 image=Image.fromarray(pixels);stream=BytesIO();image.save(stream,format='PNG');stream.seek(0)
 prs=Presentation();prs.slide_width=Pt(400);prs.slide_height=Pt(300)
 prs.slides.add_slide(prs.slide_layouts[6]).shapes.add_picture(stream,0,0,Pt(400),Pt(300))
 target=tmp_path/'colored-background.pptx';prs.save(target)
 pdf=render_presentations([target],tmp_path,Settings(renderer_path=os.environ['SMARTPPT_TEST_RENDERER']))[0]
 page=PdfReader(pdf).pages[0];assert len(page.images)==1
 assert np.array_equal(np.asarray(page.images[0].image.convert('RGB')),pixels)
 for value in page['/Resources']['/XObject'].values():
  obj=value.get_object()
  if obj.get('/Subtype')=='/Image':assert obj.get('/Filter')!='/DCTDecode'
