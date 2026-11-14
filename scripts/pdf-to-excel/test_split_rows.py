import copy,json,sys,tempfile,unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pdfplumber
from pdfplumber.utils.exceptions import MalformedPDFException
from reportlab.pdfgen import canvas
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'server/pdf-to-excel'))
import layout_split_rows as recovery
from convert import ruled_tables

class SplitRows(unittest.TestCase):
 def fixture(self,*,line_color=0,alpha=1,multiline=False,cover=False,invisible_text=False,missing_edge=False,white_text=False,decoy_lines=False,clip_text=False,overprint=False,cross_line=False,scaled_line=False):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);p=Path(tmp.name)/'source.pdf';c=canvas.Canvas(str(p),pagesize=(360,240));c.setFont('Helvetica',10)
  c.setStrokeGray(line_color);c.setStrokeAlpha(alpha)
  for x in [20,120,220,320]:
   if not(missing_edge and x==120):c.line(x,80,x,200)
  for y in [80,120,160,200]:c.line(20,y,320,y)
  c.setStrokeAlpha(1);c.setFillGray(0)
  strings=[['Name','Value','Unit'],['Inlet temperature','17.5','C'],['Outlet','18.0','C']]
  if multiline:strings[1]=['A\nB','1\n2','C\nD']
  for r,values in enumerate(strings):
   for col,text in enumerate(values):
    c.setFillAlpha(0 if invisible_text and r==1 else 1)
    c.setFillGray(1 if white_text and r==1 else 0)
    c.saveState()
    if clip_text and r==1:
     path=c.beginPath();path.rect(0,0,5,5);c.clipPath(path,stroke=0,fill=0)
    for line,s in enumerate(text.split('\n')):c.drawString(25+col*100,240-(40+r*40+14+line*12),s)
    c.restoreState()
  c.setFillAlpha(1)
  if decoy_lines:
   from reportlab.pdfbase.pdfmetrics import stringWidth
   c.setStrokeGray(0);c.setLineWidth(1)
   for col,text in enumerate(strings[1]):c.line(25+col*100,150,25+col*100+stringWidth(text,'Helvetica',10),150)
  if cover:c.setFillGray(1);c.rect(19,119,302,3,fill=1,stroke=0)
  if scaled_line:
   c.saveState();c.scale(1,20);c.setStrokeGray(1);c.setLineWidth(1);c.line(131,7,135,7);c.restoreState()
  if cross_line:
   c.setStrokeGray(1);c.setLineWidth(3);c.line(125,150,145,150)
  if overprint:
   c.setFillGray(1);c.drawString(25,146,'X')
  c.save();doc=pdfplumber.open(p);self.addCleanup(doc.close);page=doc.pages[0];native=ruled_tables(page)
  if missing_edge:return page,native,None
  t=native[0];m=copy.deepcopy(t);m['method']='layout';m['heights']=[40,20,20,40];m['cells']=[]
  for cell in t['cells']:
   if not cell['text'].strip():continue
   r,col=cell['r'],cell['c'];box=(20+col*100,40+r*40,120+col*100,80+r*40)
   glyphs=[g for g in page.chars if g['text'].strip() and box[0]<g['x0']<box[2] and box[1]<g['top']<box[3]]
   entry=dict(cell);entry['r']=0 if r==0 else (1 if col==0 else 2) if r==1 else 3
   entry['sourceTextCandidate']=[min(g['x0']for g in glyphs),min(g['top']for g in glyphs),max(g['x1']for g in glyphs),max(g['bottom']for g in glyphs)]
   m['cells'].append(entry)
  return page,native,m
 def test_visible_closed_same_line_recovers_without_changing_text(self):
  p,n,m=self.fixture();before=copy.deepcopy(m);r=recovery.recover(m,n,p)
  self.assertEqual(len(r['heights']),3);self.assertEqual(m,before)
  self.assertEqual(Counter(c['text']for c in r['cells']),Counter(c['text']for c in m['cells']))
  self.assertEqual({c['text']for c in r['cells']if c['r']==1},{'Inlet temperature','17.5','C'})
 def test_multiple_logical_lines_not_merged(self):
  p,n,m=self.fixture(multiline=True);self.assertIs(recovery.recover(m,n,p),m)
 def test_white_transparent_or_covered_rules_decline(self):
  for options in [dict(line_color=1),dict(alpha=0),dict(cover=True)]:
   p,n,m=self.fixture(**options);self.assertIs(recovery.recover(m,n,p),m)
 def test_invisible_source_text_declines(self):
  p,n,m=self.fixture(invisible_text=True);self.assertIs(recovery.recover(m,n,p),m)
 def test_unrelated_ink_does_not_prove_transparent_or_white_text(self):
  for options in [dict(invisible_text=True),dict(white_text=True),dict(clip_text=True)]:
   p,n,m=self.fixture(decoy_lines=True,**options);self.assertIs(recovery.recover(m,n,p),m)
 def test_render_failure_returns_original_and_restores_stream(self):
  p,n,m=self.fixture();position=p.pdf.stream.tell()
  for error in (RuntimeError('renderer failed'),MalformedPDFException('PDFium rejected document')):
   with patch.object(p,'to_image',side_effect=error):self.assertIs(recovery.recover(m,n,p),m)
   self.assertEqual(p.pdf.stream.tell(),position)
 def test_overprinted_white_glyph_cannot_borrow_other_text_contribution(self):
  p,n,m=self.fixture(overprint=True);self.assertIs(recovery.recover(m,n,p),m)
 def test_white_thick_line_partial_occlusion_declines(self):
  p,n,m=self.fixture(cross_line=True);self.assertIs(recovery.recover(m,n,p),m)
 def test_scaled_stroke_cannot_bypass_paint_footprint(self):
  p,n,m=self.fixture(scaled_line=True);self.assertIs(recovery.recover(m,n,p),m)
 def test_duplicate_native_ownership_declines(self):
  p,n,m=self.fixture();self.assertIs(recovery.recover(m,n+n,p),m)
 def test_crossing_span_declines(self):
  p,n,m=self.fixture();m['cells'][0]['rs']=2;self.assertIs(recovery.recover(m,n,p),m)
 def test_missing_or_changed_source_value_declines(self):
  for value in ['17.6','17.5 EXTRA']:
   p,n,m=self.fixture();next(c for c in m['cells']if c['text']=='17.5')['text']=value;self.assertIs(recovery.recover(m,n,p),m)
 def test_duplicate_model_glyph_ownership_declines(self):
  p,n,m=self.fixture();target=next(c for c in m['cells']if c['text']=='17.5');other=next(c for c in m['cells']if c['text']=='18.0');other['sourceTextCandidate']=target['sourceTextCandidate'][:];self.assertIs(recovery.recover(m,n,p),m)
 def test_resource_and_malformed_limits_decline(self):
  p,n,m=self.fixture()
  with patch.object(recovery,'physical_page',return_value=SimpleNamespace(edges=[{}]*10001)):self.assertIs(recovery.recover(m,n,p),m)
  m['heights'][0]=float('nan');self.assertIs(recovery.recover(m,n,p),m)
 def test_missing_real_boundary_declines(self):
  p,n,m=self.fixture();q,_,_=self.fixture(missing_edge=True);self.assertIs(recovery.recover(m,n,q),m)

if __name__=='__main__':unittest.main()
