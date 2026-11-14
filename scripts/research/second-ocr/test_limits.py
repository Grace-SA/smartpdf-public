import hashlib,json,sys,tempfile,time,unittest,resource
from pathlib import Path
from unittest.mock import patch
import cv2
sys.path.insert(0,str(Path(__file__).parent/'engine'))
import second_ocr

class Limits(unittest.TestCase):
 def setUp(self):
  ctx=second_ocr.research_job();self.job=ctx.__enter__();self.addCleanup(ctx.__exit__,None,None,None)
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.p=Path(self.tmp.name)
  self.config=json.loads(second_ocr.LOCK.read_text())
  from digit_fixture import digit_image
  self.image=digit_image()
 def lock(self,code=None):
  c=json.loads(json.dumps(self.config))
  if code:
   binary=self.p/'fake.py';binary.write_text('#!/usr/bin/python3\n'+code);binary.chmod(0o700)
   c['binary']=str(binary);c['sha256']['binary']=hashlib.sha256(binary.read_bytes()).hexdigest()
  path=self.p/'lock.json';path.write_text(json.dumps(c));return path
 def test_missing_binary_or_corrupt_model_declines(self):
  for key in ('binary','model'):
   c=json.loads(json.dumps(self.config));c[key]=str(self.p/'missing');p=self.p/'lock.json';p.write_text(json.dumps(c))
   with patch.object(self.job,'lock_path',p):self.assertIsNone(second_ocr.recognize(self.image))
 def test_real_timeout_is_bounded(self):
  path=self.lock('import time\ntime.sleep(10)\n');start=time.monotonic()
  with patch.object(self.job,'lock_path',path):self.assertIsNone(second_ocr.recognize(self.image))
  self.assertLess(time.monotonic()-start,3)
 def test_memory_and_output_limits_decline(self):
  for code in ['a=bytearray(512*1024*1024)\n','import sys\nsys.stdout.write("x"*1000000)\n']:
   self.job.verified=None;path=self.lock(code)
   with patch.object(self.job,'lock_path',path):self.assertIsNone(second_ocr.recognize(self.image))
 def test_call_and_pixel_budget(self):
  self.job.budget['calls']=12;self.assertIsNone(second_ocr.recognize(self.image))
  self.job.budget['calls']=0
  import numpy as np
  self.assertIsNone(second_ocr.recognize(np.zeros((129,129,3),dtype='uint8')))
 def test_real_engine_resource_measurement(self):
  start=time.monotonic();out=second_ocr.recognize(self.image)
  self.assertEqual(out[0][0],'3')
  print(json.dumps(dict(singleCallSeconds=time.monotonic()-start,childPeakRssKiB=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,word=out[0])))
if __name__=='__main__':unittest.main()
