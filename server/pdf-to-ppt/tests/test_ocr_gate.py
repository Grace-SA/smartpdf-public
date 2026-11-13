import hashlib
import pytest
from io import BytesIO
from contextlib import closing
from copy import deepcopy
from lxml import etree as ET
import numpy as np
from PIL import Image,ImageDraw
import pypdfium2 as pdfium
from pptx import Presentation
from pptx.util import Pt
from reportlab.pdfgen import canvas
from smartppt.assisted import ocr_slide
from smartppt.ocr_gate import verify_ocr_geometry
from smartppt.config import Settings


@pytest.mark.parametrize("near",[False,True])
def test_failed_line_restores_exact_pixels_and_keeps_verified_neighbor(tmp_path,monkeypatch,near):
 import smartppt.ocr_gate as gate
 # Pixel restoration is checked independently of font classification.
 monkeypatch.setattr("smartppt.assisted.latin_font",lambda *_:None)
 image=Image.new('RGB',(400,200),'white');draw=ImageDraw.Draw(image);draw.text((20,25),'BAD 123',fill='black');draw.text((20,45 if near else 105),'GOOD 456',fill='black');path=tmp_path/'scan.png';image.save(path)
 source=tmp_path/'source.pdf';c=canvas.Canvas(str(source),pagesize=image.size);c.drawImage(str(path),0,0,*image.size);c.save()
 record={'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'image_size':list(image.size),'lines':[{'text':text,'confidence':.99,'polygon':[[15,y],[150,y],[150,y+40],[15,y+40]]} for text,y in [('BAD 123',15),('GOOD 456',95)]]}
 if near:
  record['lines'][0]['polygon']=[[10,10],[150,10],[150,53],[10,53]]
  record['lines'][1]['polygon']=[[10,28],[150,28],[150,70],[10,70]]
 p=Presentation();p.slide_width=Pt(400);p.slide_height=Pt(200);slide=p.slides.add_slide(p.slide_layouts[6]);target=tmp_path/'output.pptx'
 with pdfium.PdfDocument(source) as doc,closing(doc[0]) as page:report=ocr_slide(p,slide,page,path,record,line_approvals=[True,True])
 report['page']=1;p.save(target);assert report['editable_lines']==2
 erased=report['ink_targets'][0]['erase_box']
 good=deepcopy(slide.shapes[2]._element);before=Image.open(BytesIO(slide.shapes[0].image.blob)).convert('RGB')
 monkeypatch.setattr(gate,'render_presentations',lambda *_:[source])
 monkeypatch.setattr(gate,'observed_boxes',lambda page,slide,targets:{t['shape']:t['bbox'] for t in targets})
 def measured(page,slide,targets,observed):
  return {t['shape']:(t['bbox'],[x+(3 if slide.shapes[t['shape']].text.startswith('BAD') else 0) for x in t['bbox']]) for t in targets}
 monkeypatch.setattr(gate,'raster_bounds',measured)
 verify_ocr_geometry(source,target,[report],{0:path},{0:record},Settings())
 final=Presentation(target);s=final.slides[0];assert [sh.text for sh in s.shapes if sh.has_text_frame]==['GOOD 456']
 assert ET.tostring(s.shapes[1]._element,method='c14n',exclusive=True)==ET.tostring(good,method='c14n',exclusive=True)
 result=np.array(Image.open(BytesIO(s.shapes[0].image.blob)).convert('RGB'));original=np.array(image);prior=np.array(before)
 l,t,r,b=erased
 assert np.array_equal(result[t:b,l:r],original[t:b,l:r])
 mask=np.ones(result.shape[:2],dtype=bool);mask[t:b,l:r]=False
 assert np.array_equal(result[mask],prior[mask])
 assert report['editable_lines']==1 and report['ocr_line_indices']==[1]
 assert report['geometry_rejected_line_indices']==[0]
 assert report['ocr_geometry_verification']['verified_lines']==1


def test_unverified_font_never_erases_original_pixels(tmp_path,monkeypatch):
 monkeypatch.setattr("smartppt.assisted.latin_font",lambda *_:{"error":.31})
 image=Image.new('RGB',(400,200),'white');ImageDraw.Draw(image).text((20,25),'Revenue 123.45',fill='black');path=tmp_path/'scan.png';image.save(path)
 source=tmp_path/'source.pdf';c=canvas.Canvas(str(source),pagesize=image.size);c.drawImage(str(path),0,0,*image.size);c.save()
 record={'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'image_size':list(image.size),'lines':[{'text':'Revenue 123.45','confidence':.99,'polygon':[[15,15],[170,15],[170,65],[15,65]]}]}
 prs=Presentation();prs.slide_width=Pt(400);prs.slide_height=Pt(200);slide=prs.slides.add_slide(prs.slide_layouts[6])
 with pdfium.PdfDocument(source) as doc,closing(doc[0]) as page:report=ocr_slide(prs,slide,page,path,record,line_approvals=[True])
 assert report['editable_lines']==0 and len(slide.shapes)==1
 assert 'font_shape_unverified_kept_as_image' in report['warnings']
 assert np.array_equal(np.array(Image.open(BytesIO(slide.shapes[0].image.blob)).convert('RGB')),np.array(image))
