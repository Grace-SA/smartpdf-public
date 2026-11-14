"""Real synthetic PDF evidence for vertical numeric-cell conflict refusals."""
import copy,sys,tempfile,unittest
from pathlib import Path
from reportlab.pdfgen import canvas
from pypdf import PdfReader,PdfWriter
import pdfplumber
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'server/pdf-to-excel'))
from convert import ruled_tables
from layout_numeric_guard import verify_numeric_columns
from layout_tables import LayoutError

class NumericRows(unittest.TestCase):
 def fixture(self,*,repeat=False,merged=False,cover=False,invisible=False,offset=False,rows=22):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);path=Path(tmp.name)/'source.pdf';height=rows*40+80
  c=canvas.Canvas(str(path),pagesize=(360,height));c.setFont('Helvetica',10)
  for x in [20,120,220,320]:c.line(x,40,x,height-40)
  for r in range(rows+1):
   y=height-40-r*40
   if r==6:
    c.line(20,y,120,y);c.line(220,y,320,y)
    if not merged:
     c.setStrokeGray(1 if invisible else 0);c.line(120,y,220,y);c.setStrokeGray(0)
   else:c.line(20,y,320,y)
  for r in range(rows):
   for col,value in enumerate(('Name','Value','Count')if r==0 else (f'Item {r}','25'if repeat else str(r+10),str(100+r))):c.drawString(25+col*100,height-55-r*40,value)
  if cover:c.setFillGray(1);c.rect(119,height-40-6*40-2,102,4,fill=1,stroke=0)
  c.save()
  if offset:
   reader=PdfReader(path);writer=PdfWriter();pg=writer.add_page(reader.pages[0]);pg.mediabox.lower_left=(-12,-12);pg.mediabox.upper_right=(348,height-12);writer.write(path.with_suffix('.offset.pdf'));path=path.with_suffix('.offset.pdf')
  pdf=pdfplumber.open(path);self.addCleanup(pdf.close);page=pdf.pages[0];native=ruled_tables(page);self.assertEqual(len(native),1);n=native[0];m=copy.deepcopy(n)
  for cell in m['cells']:
   r,col=cell['r'],cell['c'];top=n['bbox'][1]+sum(n['heights'][:r]);left=n['bbox'][0]+sum(n['widths'][:col]);box=(left,top,left+sum(n['widths'][col:col+cell['cs']]),top+sum(n['heights'][r:r+cell['rs']]))
   gs=[g for g in page.chars if g['text'].strip()and box[0]<(g['x0']+g['x1'])/2<box[2]and box[1]<(g['top']+g['bottom'])/2<box[3]]
   if gs:cell['sourceTextCandidate']=[min(g['x0']for g in gs),min(g['top']for g in gs),max(g['x1']for g in gs),max(g['bottom']for g in gs)]
  a=next(c for c in m['cells']if c['r']==5 and c['c']==1)
  if merged:a['rs']=1;a['text']=' '.join(a['text'].split())
  else:
   b=next(c for c in m['cells']if c['r']==6 and c['c']==1);a['text']+=' '+b['text'];a['sourceTextCandidate']=[min(a['sourceTextCandidate'][i],b['sourceTextCandidate'][i])if i<2 else max(a['sourceTextCandidate'][i],b['sourceTextCandidate'][i])for i in range(4)];m['cells'].remove(b)
  return m,native,page
 def test_vertical_mix_refuses_without_mutation(self):
  for options in ({},{'repeat':True},{'offset':True}):
   m,n,p=self.fixture(**options);before=copy.deepcopy((m,n))
   with self.assertRaisesRegex(LayoutError,'cannot safely verify'):verify_numeric_columns(m,n,p)
   self.assertEqual((m,n),before)
 def test_legal_model_rowspan_not_split(self):
  m,n,p=self.fixture();next(c for c in m['cells']if c['r']==5 and c['c']==1)['rs']=2;verify_numeric_columns(m,n,p)
 def test_source_merged_and_same_cell_wrapped_values_not_split(self):
  m,n,p=self.fixture(merged=True);verify_numeric_columns(m,n,p)
 def test_covered_and_invisible_shared_boundary_not_proof(self):
  for options in ({'cover':True},{'invisible':True}):
   m,n,p=self.fixture(**options);verify_numeric_columns(m,n,p)
 def test_competing_model_owner_is_ambiguous(self):
  m,n,p=self.fixture();a=copy.deepcopy(next(c for c in m['cells']if c['r']==5 and c['c']==1));a['r']=6;m['cells'].append(a);verify_numeric_columns(m,n,p)
 def test_nested_or_duplicate_grid_not_proof(self):
  m,n,p=self.fixture();verify_numeric_columns(m,n+[copy.deepcopy(n[0])],p)
 def test_date_fraction_and_units_not_inferred(self):
  for text in ['25 12/14/15','25 1/2','25 USD']:
   m,n,p=self.fixture();next(c for c in m['cells']if c['r']==5 and c['c']==1)['text']=text;verify_numeric_columns(m,n,p)
 def test_nonadjacent_source_rows_not_combined(self):
  m,n,p=self.fixture();a=next(c for c in m['cells']if c['r']==5 and c['c']==1);b=next(c for c in m['cells']if c['r']==7 and c['c']==1);a['text']='15 '+b['text'];a['sourceTextCandidate'][3]=b['sourceTextCandidate'][3];verify_numeric_columns(m,n,p)
 def test_small_table_outside_scope(self):
  m,n,p=self.fixture(rows=10);verify_numeric_columns(m,n,p)
 def test_reversed_tokens_do_not_match_counter(self):
  m,n,p=self.fixture();a=next(c for c in m['cells']if c['r']==5 and c['c']==1);a['text']=' '.join(reversed(a['text'].split()));verify_numeric_columns(m,n,p)
if __name__=='__main__':unittest.main()
