import sys,tempfile,unittest,copy
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from PIL import Image,ImageDraw
from pypdf import PdfReader,PdfWriter
from pypdf.generic import NameObject,DictionaryObject,NumberObject,ArrayObject
import pdfplumber
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'server/pdf-to-excel'))
from field_visibility import verify
from layout_tables import LayoutError
class FieldVisibility(unittest.TestCase):
 def fixture(self,kind):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);path=Path(tmp.name)/'source.pdf';c=canvas.Canvas(str(path),pagesize=(400,300));c.setFont('Helvetica',14)
  form=kind in ['form','form_visible']
  if form:c.beginForm('number',0,0,400,300)
  if kind=='clip':
   c.saveState();p=c.beginPath();p.rect(0,0,1,1);c.clipPath(p,stroke=0,fill=0)
  if kind in ['transparent','scan']:c.setFillAlpha(0)
  if kind=='tiny':c.setFont('Helvetica',.1)
  if kind=='same_gray':
   c.setFillColorRGB(1,0,0);c.rect(0,0,400,300,fill=1,stroke=0);c.setFillColorRGB(0,.509,0)
  if kind=='faint':c.setFillColorRGB(.999,.999,.999)
  if kind=='thin':
   t=c.beginText(100,150);t.setFont('Helvetica',14);t.setHorizScale(1);t.textOut('888');c.drawText(t)
  elif kind=='outline':
   t=c.beginText(100,150);t.setFont('Helvetica',14);t.setTextRenderMode(1);t.textOut('888');c.drawText(t)
  else:c.drawString(100,150,'888')
  if kind=='overprint':c.drawString(100,150,'888')
  if kind=='clip':c.restoreState()
  if kind in ['white','black','color','form']:
   c.setFillColorRGB(*({'black':(0,0,0),'color':(.2,.5,.8)}.get(kind,(1,1,1))))
   # Fill the whole padded glyph region, not only the glyph's nominal box.
   c.rect(80,125,75,55,fill=1,stroke=0)
  if form:c.endForm();c.doForm('number')
  if kind=='scan':
   c.setFillAlpha(1);img=Image.new('RGB',(100,60),'white');ImageDraw.Draw(img).text((20,20),'888',fill='black');c.drawImage(ImageReader(img),85,130,60,40)
  if kind=='neighbor':c.drawString(125,150,'9')
  if kind=='noise':c.setFillGray(1);c.rect(80,125,75,55,fill=1,stroke=0);c.setFillGray(0);c.circle(110,150,1,fill=1,stroke=0)
  c.save()
  if kind=='custom_widths':
   reader=PdfReader(path);w=PdfWriter();p=w.add_page(reader.pages[0]);f=next(iter(p['/Resources']['/Font'].values())).get_object();f[NameObject('/Widths')]=ArrayObject([NumberObject(600)]);w.write(path)
  doc=pdfplumber.open(path);self.addCleanup(doc.close);p=doc.pages[0];gs=[g for g in p.chars if g['text']=='8'];box=[min(g['x0']for g in gs),min(g['top']for g in gs),max(g['x1']for g in gs),max(g['bottom']for g in gs)]
  return {'cells':[dict(text='888',sourceTextCandidate=box)]},p
 def test_uniform_cover_clip_alpha_form_refused(self):
  for kind in ['white','black','color','clip','transparent','form']:
   m,p=self.fixture(kind);before=copy.deepcopy(m)
   with self.assertRaisesRegex(LayoutError,'could not be verified'):verify(m,p)
   self.assertEqual(m,before)
 def test_visible_and_nonuniform_cases_not_certified_or_refused(self):
  for kind in ['plain','overprint','same_gray','outline','scan','form_visible','neighbor','noise','faint']:
   m,p=self.fixture(kind);verify(m,p)
 def test_small_or_untrusted_font_scope_declines(self):
  for kind in ['tiny','thin','custom_widths']:
   m,p=self.fixture(kind);verify(m,p)
 def test_ambiguous_ownership_not_proof(self):
  m,p=self.fixture('white');m['cells'].append(copy.deepcopy(m['cells'][0]));verify(m,p)
 def test_actual_render_dimensions_must_match_budget(self):
  import numpy as np
  from types import SimpleNamespace
  from unittest.mock import patch
  for shape in [(1,20_000_001,3),(1,1,3)]:
   m,p=self.fixture('white');arr=np.broadcast_to(np.zeros((1,1,3),dtype=np.uint8),shape)
   image=SimpleNamespace(original=SimpleNamespace(convert=lambda mode:arr))
   with patch.object(p,'to_image',return_value=image):verify(m,p)
 def test_visible_annotation_not_ignored(self):
  from pypdf.generic import DecodedStreamObject
  m,p=self.fixture('transparent');w=PdfWriter();page=w.add_page(PdfReader(p.pdf.stream).pages[0])
  ap=DecodedStreamObject();ap.set_data(b'q 0 g BT /F1 14 Tf 10 15 Td (888) Tj ET Q')
  ap.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Form'),NameObject('/BBox'):ArrayObject([NumberObject(v)for v in [0,0,50,40]]),NameObject('/Resources'):page['/Resources']})
  annot=DictionaryObject({NameObject('/Type'):NameObject('/Annot'),NameObject('/Subtype'):NameObject('/Stamp'),NameObject('/Rect'):ArrayObject([NumberObject(v)for v in [90,135,140,175]]),NameObject('/F'):NumberObject(4),NameObject('/AP'):DictionaryObject({NameObject('/N'):w._add_object(ap)})})
  page[NameObject('/Annots')]=ArrayObject([w._add_object(annot)])
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);path=Path(tmp.name)/'annot.pdf';w.write(path)
  doc=pdfplumber.open(path);self.addCleanup(doc.close);verify(m,doc.pages[0])
 def test_native_typography_box_fallback_requires_source_evidence(self):
  m,p=self.fixture('white');c=m['cells'][0];c['sourceTextBox']=c.pop('sourceTextCandidate');c['sourceFont']=True
  with self.assertRaises(LayoutError):verify(m,p)
  c['sourceFont']=False;verify(m,p)
if __name__=='__main__':unittest.main()
