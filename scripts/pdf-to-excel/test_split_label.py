"""Synthetic source-cell label joins, preserving all other workbook fields."""
import copy,sys,unittest,io
from unittest.mock import patch
from reportlab.pdfgen import canvas
from pypdf import PdfReader,PdfWriter
import pdfplumber
from pdfplumber.utils.exceptions import MalformedPDFException
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'server/pdf-to-excel'))
import test_split_rows
from layout_split_label import recover

class SplitLabel(unittest.TestCase):
 def fixture(self,**options):
  p,n,_=test_split_rows.SplitRows.fixture(self,**options);t=n[0];m=copy.deepcopy(t);m['widths']=[50,50,100,100];m['cells']=[]
  for orig in t['cells']:
   c=copy.deepcopy(orig);r,col=c['r'],c['c'];box=(20+col*100,40+r*40,120+col*100,80+r*40)
   glyphs=[g for g in p.chars if g['text'].strip()and box[0]<(g['x0']+g['x1'])/2<box[2]and box[1]<(g['top']+g['bottom'])/2<box[3]]
   if not glyphs:continue
   def bounds(gs):return [min(g['x0']for g in gs),min(g['top']for g in gs),max(g['x1']for g in gs),max(g['bottom']for g in gs)]
   if r==1 and col==0:
    # Literal source space separates these existing model fragments.
    glyphs.sort(key=lambda g:g['x0']);a=copy.deepcopy(c);b=copy.deepcopy(c)
    a.update(c=0,cs=1,text='Inlet',sourceTextCandidate=bounds(glyphs[:5]));b.update(c=1,cs=1,text='temperature',sourceTextCandidate=bounds(glyphs[5:]));m['cells'] += [a,b]
   else:
    c.update(c=col+1 if col else 0,cs=1 if col else 2,sourceTextCandidate=bounds(glyphs));m['cells'].append(c)
  return m,n,p
 def test_exact_single_space_label_reunites_only_two_cells(self):
  m,n,p=self.fixture();before=copy.deepcopy(m);r=recover(m,n,p);self.assertEqual(m,before)
  target=next(c for c in r['cells']if c['r']==1 and c['c']==0)
  self.assertEqual((target['text'],target['cs']),('Inlet temperature',2))
  self.assertFalse(any(c['r']==1 and c['c']==1 for c in r['cells']))
  unchanged=lambda t:[c for c in t['cells']if not(c['r']==1 and c['c']in(0,1))]
  self.assertEqual(unchanged(r),unchanged(m));self.assertEqual((r['widths'],r['heights']),(m['widths'],m['heights']))
 def test_hidden_overprinted_clipped_and_painted_labels_unchanged(self):
  for opts in ({'invisible_text':True},{'white_text':True},{'clip_text':True},{'overprint':True},{'scaled_line':True},{'cover':True}):
   m,n,p=self.fixture(**opts);self.assertIs(recover(m,n,p),m)
 def test_invisible_or_transparent_borders_not_proof(self):
  for opts in ({'line_color':1},{'alpha':0}):
   m,n,p=self.fixture(**opts);self.assertIs(recover(m,n,p),m)
 def test_actual_literal_space_required(self):
  m,n,p=self.fixture()
  for g in p.chars:
   if g['text']==' ':g['text']=''
  self.assertIs(recover(m,n,p),m)
 def test_large_real_word_gap_and_two_lines_not_joined(self):
  original=canvas.Canvas.drawString
  for multiline in (False,True):
   def draw(c,x,y,text,*args,**kwargs):
    if text=='Inlet temperature':
     if multiline:
      original(c,x,y,'Inlet');original(c,x,y-12,'temperature')
     else:
      t=c.beginText(x,y);t.setWordSpace(15);t.textOut(text);c.drawText(t)
    else:original(c,x,y,text,*args,**kwargs)
   with patch.object(canvas.Canvas,'drawString',draw):m,n,p=self.fixture()
   self.assertIs(recover(m,n,p),m)
 def test_real_mixed_font_label_not_flattened(self):
  original=canvas.Canvas.drawString
  def draw(c,x,y,text,*args,**kwargs):
   if text=='Inlet temperature':
    t=c.beginText(x,y);t.setFont('Helvetica',10);t.textOut('Inlet tem');t.setFont('Helvetica-Bold',10);t.textOut('perature');c.drawText(t)
   else:original(c,x,y,text,*args,**kwargs)
  with patch.object(canvas.Canvas,'drawString',draw):m,n,p=self.fixture()
  self.assertIs(recover(m,n,p),m)
 def test_real_white_stroke_across_label_declines(self):
  m,n,p=self.fixture();overlay=io.BytesIO();c=canvas.Canvas(overlay,pagesize=(360,240));c.setStrokeGray(1);c.setLineWidth(3);c.line(25,150,100,150);c.save()
  p.pdf.stream.seek(0);reader=PdfReader(p.pdf.stream);writer=PdfWriter();page=writer.add_page(reader.pages[0]);page.merge_page(PdfReader(overlay).pages[0]);result=io.BytesIO();writer.write(result);new=pdfplumber.open(result);self.addCleanup(new.close)
  self.assertIs(recover(m,n,new.pages[0]),m)
 def test_reversed_text_truncated_word_and_hyphen_not_joined(self):
  for text in ['temperature','Inle','Inlet-','Inlet:','17']:
   m,n,p=self.fixture();next(c for c in m['cells']if c['r']==1 and c['c']==0)['text']=text
   self.assertIs(recover(m,n,p),m)
 def test_overlapping_rowspan_or_third_owner_declines(self):
  m,n,p=self.fixture();a=copy.deepcopy(next(c for c in m['cells']if c['r']==1 and c['c']==0));a.update(r=0,rs=2);m['cells'].append(a);self.assertIs(recover(m,n,p),m)
  m,n,p=self.fixture();a=copy.deepcopy(next(c for c in m['cells']if c['r']==1 and c['c']==0));a.update(r=2,c=3);m['cells']=[c for c in m['cells']if not(c['r']==2 and c['c']==3)]+[a];self.assertIs(recover(m,n,p),m)
 def test_render_failure_leaves_model_unchanged(self):
  m,n,p=self.fixture()
  with patch.object(p,'to_image',side_effect=MalformedPDFException('unavailable render')):self.assertIs(recover(m,n,p),m)
 def test_recovery_is_idempotent(self):
  m,n,p=self.fixture();r=recover(m,n,p);self.assertIs(recover(r,n,p),r)
 def test_duplicate_native_table_declines(self):
  m,n,p=self.fixture();self.assertIs(recover(m,n+[copy.deepcopy(n[0])],p),m)
 def test_distinct_glyph_baselines_decline(self):
  m,n,p=self.fixture()
  for g in p.chars:
   if 80<g['top']<120 and g['x0']>50 and g['x0']<120:g['matrix']=(*g['matrix'][:5],g['matrix'][5]+3)
  self.assertIs(recover(m,n,p),m)
if __name__=='__main__':unittest.main()
