"""Model-boundary integration: structural refusal precedes atomic publication."""
import os,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'server/pdf-to-excel'))
import convert as engine
import test_record_order_guard as fixtures

class RecordOrderIntegration(unittest.TestCase):
 fixture=fixtures.RecordOrder.fixture
 def test_conflicting_model_preserves_existing_output(self):
  source,model,_=self.fixture(named=True);out=source.parent/'out.xlsx';out.write_bytes(b'keep prior workbook');before=source.read_bytes()
  with patch.dict(os.environ,{'PDF_EXCEL_MODELS':'model-double'}),patch.object(engine,'extract_layout_tables',return_value={0:[model]}):
   with self.assertRaisesRegex(engine.ConversionError,'separately positioned source records'):engine.convert(source,out,{'ocr':False})
  self.assertEqual(out.read_bytes(),b'keep prior workbook');self.assertEqual(source.read_bytes(),before)
 def test_conflicting_model_creates_no_new_output(self):
  source,model,_=self.fixture();out=source.parent/'out.xlsx';before=source.read_bytes()
  with patch.dict(os.environ,{'PDF_EXCEL_MODELS':'model-double'}),patch.object(engine,'extract_layout_tables',return_value={0:[model]}):
   with self.assertRaisesRegex(engine.ConversionError,'separately positioned source records'):engine.convert(source,out,{'ocr':False})
  self.assertFalse(out.exists());self.assertEqual(source.read_bytes(),before)

if __name__=='__main__':unittest.main()
