"""Synthetic visible-grid numeric conflict and no-mutation regressions."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pdfplumber
from reportlab.pdfgen import canvas
from pdfplumber.utils.exceptions import MalformedPDFException
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'server/pdf-to-excel'))
from convert import ruled_tables
from layout_tables import LayoutError
from layout_numeric_guard import verify_numeric_columns

class NumericGuard(unittest.TestCase):
 def fixture(self, color=False, repeated=False, hide_lines=False, cover_lines=False, transparent=False, reverse=False, merged=False, wrapped=False):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);path=Path(tmp.name)/'grid.pdf'
  c=canvas.Canvas(str(path),pagesize=(360,300));c.setFont('Helvetica',10)
  if reverse:c.setFillColorRGB(.2,0,.4);c.rect(20,40,300,240,fill=1,stroke=0)
  c.setStrokeColorRGB(*((1,1,1) if hide_lines else (.5,0,.5) if color else (0,0,0)))
  for x in ((20,120,320) if merged else (20,120,220,320)):c.line(x,40,x,280)
  for y in range(40,281,40):c.line(20,y,320,y)
  c.setFillColorRGB(*((1,1,1) if reverse else (0,0,.5) if color else (0,0,0)))
  c.setFillAlpha(0 if transparent else 1)
  for r in range(6):
   for col,value in enumerate(('ID', 'Rate','Count') if r==0 else (str(r), '12.3' if repeated else f'{r}.3', '12.3' if repeated else str(400+r))):
    c.drawString(125 if wrapped and col==2 else 25+col*100,
                 253-r*40 if wrapped and col==2 else 265-r*40,value)
  c.setFillAlpha(1)
  if cover_lines:
   c.setFillGray(1);c.rect(218,39,4,242,fill=1,stroke=0)
  c.save();pdf=pdfplumber.open(path);self.addCleanup(pdf.close);p=pdf.pages[0];native=ruled_tables(p);n=native[0];m=copy.deepcopy(n);m['cells']=[];m['widths']=[100,200]
  for r in range(6):
   for col,sourcecols in [(0,[0]),(1,[1,2])]:
    originals=[z for z in n['cells']if z['r']==r and z['c']in sourcecols]
    box=(20+sourcecols[0]*100,20+r*40,20+(sourcecols[-1]+1)*100,60+r*40)
    gs=[g for g in p.chars if box[0]<(g['x0']+g['x1'])/2<box[2] and box[1]<(g['top']+g['bottom'])/2<box[3]]
    m['cells'].append(dict(r=r,c=col,rs=1,cs=1,text=' '.join(z['text']for z in originals),sourceTextCandidate=[min(g['x0']for g in gs),min(g['top']for g in gs),max(g['x1']for g in gs),max(g['bottom']for g in gs)]))
  return m,native,p
 def test_repeated_visible_numeric_collapse_refuses_without_mutation(self):
  for options in ({},{'color':True},{'repeated':True},{'transparent':True}):
   m,n,p=self.fixture(**options);before=copy.deepcopy((m,n))
   with self.assertRaisesRegex(LayoutError,'cannot safely verify'):verify_numeric_columns(m,n,p)
   self.assertEqual((m,n),before)
 def test_legal_separate_columns_and_header_spans(self):
  m,n,p=self.fixture();legal=copy.deepcopy(n[0]);verify_numeric_columns(legal,n,p)
  m['cells']=[c for c in m['cells']if c['r']<3];verify_numeric_columns(m,n,p)
 def test_invisible_or_covered_divider_is_not_evidence(self):
  for kwargs in ({'hide_lines':True},{'cover_lines':True}):
   m,n,p=self.fixture(**kwargs);verify_numeric_columns(m,n,p)
 def test_duplicate_source_table_has_no_unique_owner(self):
  m,n,p=self.fixture();verify_numeric_columns(m,n+[copy.deepcopy(n[0])],p)
 def test_repeated_model_rows_do_not_create_evidence(self):
  m,n,p=self.fixture()
  for c in m['cells']:c['r']=0
  verify_numeric_columns(m,n,p)
 def test_source_span_or_multiline_value_not_guessed(self):
  for text in ('12\n34','(12)','12-34','1/2','USD 12'):
   m,n,p=self.fixture()
   for c in m['cells']:
    if c['c']==1:c['text']=text
   verify_numeric_columns(m,n,p)
 def test_swapped_values_do_not_match_by_counter(self):
  m,n,p=self.fixture()
  for c in m['cells']:c['text']=' '.join(reversed(c['text'].split()))
  verify_numeric_columns(m,n,p)
 def test_real_source_merged_and_wrapped_numeric_cells(self):
  for kwargs in ({'merged':True},{'merged':True,'wrapped':True}):
   m,n,p=self.fixture(**kwargs);verify_numeric_columns(m,n,p)
 def test_malformed_transform_and_model_indices_do_not_prove_conflict(self):
  for value in (float('nan'),float('inf')):
   m,n,p=self.fixture()
   for g in p.chars:g['matrix']=(*g['matrix'][:5],value)
   verify_numeric_columns(m,n,p)
  m,n,p=self.fixture()
  for c in m['cells']:c['r']=float(c['r'])
  verify_numeric_columns(m,n,p)
 def test_render_failure_is_optional_detection_not_repair(self):
  m,n,p=self.fixture()
  with patch.object(p,'to_image',side_effect=MalformedPDFException('bad render')):verify_numeric_columns(m,n,p)
 def test_reverse_text_does_not_enable_reconstruction(self):
  m,n,p=self.fixture(reverse=True)
  before=copy.deepcopy((m,n))
  with self.assertRaises(LayoutError):verify_numeric_columns(m,n,p)
  self.assertEqual((m,n),before)
if __name__=='__main__':unittest.main()
