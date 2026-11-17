import os
from contextlib import closing
import pytest
import pypdfium2 as pdfium
from pptx import Presentation
from pptx.util import Pt
from reportlab.pdfgen import canvas
from smartppt.layout import add_text
from smartppt.config import Settings

@pytest.mark.skipif(not os.getenv('SMARTPPT_TEST_RENDERER'),reason='real Office renderer required')
@pytest.mark.parametrize('visual_pass',[True,False])
def test_one_bad_fit_does_not_discard_verified_neighbor(tmp_path,monkeypatch,visual_pass):
 import smartppt.ocr_fit as fitter
 source=tmp_path/'source.pdf';c=canvas.Canvas(str(source),pagesize=(300,400));c.setFont('Helvetica',12)
 c.drawString(40,330,'Total 123.45');c.drawString(40,230,'Cost 67.89');c.save()
 p=Presentation();p.slide_width=Pt(300);p.slide_height=Pt(400);slide=p.slides.add_slide(p.slide_layouts[6])
 for text,y in [('Total 123.45',56),('Cost 67.89',156)]:add_text(slide,text,42,y,150,22,12)
 target=tmp_path/'output.pptx';p.save(target);originals=[s._element.xml for s in Presentation(target).slides[0].shapes]
 rough=[{'shape':i,'bbox':[40,60+100*i,110,72+100*i]} for i in range(2)]
 with pdfium.PdfDocument(source) as doc,closing(doc[0]) as page:boxes=fitter.observed_boxes(page,slide,rough)
 assert len(boxes)==2
 targets=[]
 for i,(l,t,r,b) in boxes.items():targets.append({'shape':i,'bbox':[l,t,r,b],'quad':[(l,t),(r,t),(r,b),(l,b)]})
 report=[{'page':1,'route':'paddle-ocr','ink_targets':targets}];fit=fitter.fit_shape
 def imperfect_fit(shape,desired,observed):
  changed=fit(shape,desired,observed)
  if changed and shape.text.startswith('Cost'):shape.left+=Pt(15)
  return changed
 monkeypatch.setattr(fitter,'fit_shape',imperfect_fit)
 # Geometry is measured by the real renderer; separately exercise final page
 # appearance rejection without depending on antialiasing noise.
 monkeypatch.setattr(fitter,'accept_candidate',lambda *_:visual_pass)
 fitter._fit_ocr_pages(source,target,report,Settings(renderer_path=os.environ['SMARTPPT_TEST_RENDERER']))
 result=Presentation(target);fit_report=report[0]['font_fit']
 assert fit_report['partial_fit_independently_rendered']
 assert fit_report['accepted']==visual_pass
 assert fit_report['accepted_lines']==(1 if visual_pass else 0)
 assert result.slides[0].shapes[1]._element.xml==originals[1]
 if visual_pass:assert result.slides[0].shapes[0]._element.xml!=originals[0]
 else:assert result.slides[0].shapes[0]._element.xml==originals[0]
 assert [s.text for s in result.slides[0].shapes]==['Total 123.45','Cost 67.89']
