"""Synthetic rendered PDF proofs and counterexamples for header-band recovery."""
import copy,sys,tempfile,unittest
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
import pdfplumber
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'server/pdf-to-excel'))
from layout_header_band import recover
class HeaderBand(unittest.TestCase):
 def fixture(self,*,cover=False,white=False,gap=False,cross=False,side=False,rows=4,hidden=False):
  t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);path=Path(t.name)/'source.pdf';c=canvas.Canvas(str(path),pagesize=(500,500));c.setFont('Helvetica',10);c.setLineWidth(0)
  for top in [100,120,140,160,180,200]:
   c.setFillGray(1 if white else 0);c.rect(20,500-top-.4,460,.4,fill=1,stroke=0)
  c.setFillGray(0)
  if gap:
   c.rect(250,380, .4,5,fill=1,stroke=0);c.rect(250,395,.4,5,fill=1,stroke=0)
  else:c.rect(250,300,.4,100,fill=1,stroke=0)
  c.drawString(40,388,'Indicator')
  if hidden:
   z=c.beginText(280,388);z.setFont('Helvetica',10);z.setTextRenderMode(3);z.textOut('Weight of items');c.drawText(z)
  else:c.drawString(280,388,'Weight of items')
  c.drawString(450,405,'(%)')
  if cross:c.drawString(245,388,'X')
  if side:c.drawString(270,389,'Note')
  for r in range(rows):c.drawString(40,368-r*20,'Record '+str(r));c.drawString(340,368-r*20,str(10+r))
  if cover:c.setFillGray(1);c.rect(279,386,35,15,fill=1,stroke=0)
  c.save();doc=pdfplumber.open(path);self.addCleanup(doc.close);p=doc.pages[0]
  cells=[dict(r=0,c=0,rs=1,cs=1,text='Indicator',sourceTextCandidate=[39,103,100,116]),dict(r=0,c=1,rs=1,cs=1,text='(%) items',sourceTextCandidate=[280+stringWidth('Weight of ','Helvetica',10),85,480,116])]
  for r in range(rows):
   for col,x,text in [(0,40,'Record '+str(r)),(1,340,str(10+r))]:cells.append(dict(r=r+1,c=col,rs=1,cs=1,text=text,sourceTextCandidate=[x-1,123+r*20,x+45,136+r*20]))
  return dict(cells=cells,widths=[230,230],heights=[35]+[20]*rows,bbox=[20,85,480,200]),p
 def test_recovers_header_and_preserves_unit_and_body(self):
  m,p=self.fixture();before=copy.deepcopy(m);n=recover(m,p)
  self.assertEqual(n['cells'][1]['text'],'Weight of items');self.assertEqual(n['sourceHeaderContext'],'(%)');self.assertEqual(m,before)
  self.assertEqual(n['cells'][2:],m['cells'][2:]);self.assertEqual(n['widths'],m['widths']);self.assertEqual(n['heights'],m['heights']);self.assertEqual(recover(n,p),n)
 def test_covered_white_hidden_and_missing_rule_decline(self):
  for o in [dict(cover=True),dict(white=True),dict(hidden=True),dict(gap=True)]:
   m,p=self.fixture(**o);self.assertEqual(recover(m,p),m)
 def test_crossing_and_competing_header_text_decline(self):
  for o in [dict(cross=True),dict(side=True)]:
   m,p=self.fixture(**o);self.assertEqual(recover(m,p),m)
 def test_four_complete_records_required(self):
  m,p=self.fixture(rows=3);self.assertEqual(recover(m,p),m)
 def test_model_misalignment_and_ownership_conflict(self):
  m,p=self.fixture();m['cells'][-1]['sourceTextCandidate']=[40,183,80,196];self.assertEqual(recover(m,p),m)
  m,p=self.fixture();m['cells'].append(copy.deepcopy(m['cells'][0]));self.assertEqual(recover(m,p),m)
 def test_does_not_rewrite_numeric_prefix_or_wrong_suffix(self):
  for text in ['(%) wrong','42 items','(%) 2006','items']:
   m,p=self.fixture();m['cells'][1]['text']=text;self.assertEqual(recover(m,p),m)
 def test_repeated_source_rows_not_independent(self):
  m,p=self.fixture()
  for cell in m['cells'][2:]:cell['sourceTextCandidate']=copy.deepcopy(m['cells'][2+cell['c']]['sourceTextCandidate'])
  self.assertEqual(recover(m,p),m)
 def test_existing_context_not_overwritten(self):
  m,p=self.fixture();m['sourceHeaderContext']='keep me';self.assertEqual(recover(m,p),m)
 def test_competing_header_owner(self):
  m,p=self.fixture();m['cells'][0]['sourceTextCandidate'][2]=480;self.assertEqual(recover(m,p),m)
 def test_missing_font_identity(self):
  m,p=self.fixture()
  for g in p.chars:g['fontname']=None
  self.assertEqual(recover(m,p),m)
 def test_workbook_delivers_unit_comment_without_losing_context(self):
  from convert import write_workbook
  from openpyxl import load_workbook
  m,p=self.fixture();n=recover(m,p);n.update(page=1,index=1,sourceContext='Original title')
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);out=Path(tmp.name)/'out.xlsx'
  write_workbook([n],out,'tables');book=load_workbook(out);self.addCleanup(book.close)
  self.assertEqual(book.active['B1'].value,'Weight of items')
  self.assertIn('Original title',book.active['A1'].comment.text)
  self.assertIn('not inferred:\n(%)',book.active['A1'].comment.text)
  self.assertEqual(book.active['B2'].value,'10')
if __name__=='__main__':unittest.main()
