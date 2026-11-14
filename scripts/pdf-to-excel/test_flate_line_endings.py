"""Bounded Flate compatibility, never arbitrary trailing data tolerance."""
import base64,sys,unittest,zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'server/pdf-to-excel'))
from pypdf.generic import EncodedStreamObject,NameObject,ArrayObject
from source_hidden_ocr import bounded_content,Unsupported
class FlateLineEndings(unittest.TestCase):
 def stream(self,data,filters='/FlateDecode'):
  s=EncodedStreamObject();s._data=data;s[NameObject('/Filter')]=NameObject(filters)if isinstance(filters,str)else ArrayObject([NameObject(v)for v in filters]);return s
 def test_single_line_endings(self):
  raw=b'BT (visible text) Tj ET '*20
  for suffix in [b'',b'\n',b'\r',b'\r\n']:
   s=self.stream(zlib.compress(raw)+suffix);before=s._data
   self.assertEqual(bounded_content(s,len(raw)),raw);self.assertEqual(s._data,before);self.assertIsNone(s.decoded_self)
 def test_arbitrary_trailing_data_rejected(self):
  for suffix in [b' ',b'\x00',b'\t',b'\n\n',b'\nX',b'\r\nX',b'\n'*100,zlib.compress(b'evil'),b'\n'+zlib.compress(b'evil')]:
   with self.assertRaises(Unsupported):bounded_content(self.stream(zlib.compress(b'good'*30)+suffix),1000)
 def test_truncation_and_checksum(self):
  raw=zlib.compress(b'good'*30)
  for data in [raw[:-1],raw[:-4],raw[:-1]+bytes([raw[-1]^1]),b'not zlib']:
   with self.assertRaises(Unsupported):bounded_content(self.stream(data),1000)
 def test_exact_and_excess_output_budget(self):
  raw=b'X'*1000;s=self.stream(zlib.compress(raw)+b'\n')
  self.assertEqual(bounded_content(s,1000),raw)
  for cap in [999,20,0,-1]:
   with self.assertRaises(Unsupported):bounded_content(s,cap)
 def test_compressed_input_budget_stays_enforced(self):
  with self.assertRaises(Unsupported):bounded_content(self.stream(zlib.compress(b'A')+b'\n'),1)
 def test_filter_chain(self):
  raw=b'BT (sample) Tj ET '*100
  s=self.stream(base64.a85encode(zlib.compress(raw)+b'\r\n',adobe=True),['/ASCII85Decode','/FlateDecode'])
  self.assertEqual(bounded_content(s,10000),raw)
  s=self.stream(base64.a85encode(zlib.compress(raw)+b'\nX',adobe=True),['/ASCII85Decode','/FlateDecode'])
  with self.assertRaises(Unsupported):bounded_content(s,10000)
if __name__=='__main__':unittest.main()
