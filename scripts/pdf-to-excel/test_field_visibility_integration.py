"""Real conversion and atomic-output checks for uniform numeric-field refusals."""
import os,sys,tempfile,unittest
from pathlib import Path
from reportlab.pdfgen import canvas
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'server/pdf-to-excel'))
from convert import convert,ConversionError

@unittest.skipUnless(os.environ.get('PDF_EXCEL_MODELS'),'Local table models required')
class FieldVisibilityIntegration(unittest.TestCase):
 def fixture(self,kind):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=Path(tmp.name);path=root/'source.pdf'
  c=canvas.Canvas(str(path),pagesize=(600,400));c.setFont('Helvetica',14)
  for x in [50,250,450]:c.line(x,100,x,300)
  for y in [100,150,200,250,300]:c.line(50,y,450,y)
  for r,(a,b)in enumerate([('Item','Amount'),('Alpha','100'),('Beta','888'),('Gamma','300')]):
   y=275-r*50;c.drawString(65,y,a)
   if kind=='clip'and r==2:
    c.saveState();p=c.beginPath();p.rect(0,0,1,1);c.clipPath(p,stroke=0,fill=0);c.drawString(270,y,b);c.restoreState()
   else:c.drawString(270,y,b)
  if kind=='cover':c.setFillGray(1);c.rect(268,172,45,17,fill=1,stroke=0)
  c.save();return path,root/'output.xlsx'
 def test_actual_cover_refusal_preserves_existing_output(self):
  source,out=self.fixture('cover');before=source.read_bytes();out.write_bytes(b'keep-existing-output')
  with self.assertRaisesRegex(ConversionError,'numeric field could not be verified'):convert(source,out,{'ocr':False})
  self.assertEqual(out.read_bytes(),b'keep-existing-output');self.assertEqual(source.read_bytes(),before)
  self.assertFalse(list(out.parent.glob('.pdf-excel-workbook-*')))
 def test_actual_clip_refusal_does_not_create_output(self):
  source,out=self.fixture('clip');before=source.read_bytes()
  with self.assertRaisesRegex(ConversionError,'numeric field could not be verified'):convert(source,out,{'ocr':False})
  self.assertFalse(out.exists());self.assertEqual(source.read_bytes(),before)
if __name__=='__main__':unittest.main()
