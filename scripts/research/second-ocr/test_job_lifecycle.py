import concurrent.futures
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'engine'))
sys.path.insert(0,str(ROOT))
import second_ocr
import supervised_job
from digit_fixture import digit_image

class Jobs(unittest.TestCase):
 def test_default_off(self):
  self.assertIsNone(second_ocr.recognize(digit_image()))
  import ocr_missing_digits
  with patch("ocr_missing_digits.glyph",side_effect=AssertionError("unexpected glyph work")):
   self.assertEqual(ocr_missing_digits.recover(None,[],None,None,None,None),([],0))
 def test_context_isolation_and_exception_cleanup(self):
  with tempfile.TemporaryDirectory() as root:
   with second_ocr.research_job(temp_parent=root) as outer:
    outer.budget['calls']=12
    self.assertIsNone(second_ocr.recognize(digit_image()))
    with self.assertRaises(RuntimeError):
     with second_ocr.research_job(temp_parent=root) as inner:
      folder=Path(inner.folder)
      self.assertEqual(second_ocr.recognize(digit_image())[0][0],'3')
      self.assertEqual(inner.budget['calls'],1)
      raise RuntimeError('cancelled')
    self.assertFalse(folder.exists());self.assertTrue(inner.closed)
    self.assertIsNone(inner.recognize(digit_image()))
    self.assertIs(second_ocr._current.get(),outer)
   self.assertEqual(list(Path(root).iterdir()),[])
  self.assertIsNone(second_ocr._current.get())
 def test_concurrent_independent_job_budgets(self):
  def one(exhaust):
   with second_ocr.research_job() as job:
    if exhaust:job.budget['calls']=12
    result=second_ocr.recognize(digit_image())
    return result,job.budget['calls'],job.folder
  with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
   a,b=list(pool.map(one,[True,False]))
  self.assertIsNone(a[0]);self.assertEqual(a[1],12)
  self.assertEqual(b[0][0][0],'3');self.assertEqual(b[1],1)
  self.assertNotEqual(a[2],b[2]);self.assertFalse(Path(a[2]).exists());self.assertFalse(Path(b[2]).exists())
 def test_shared_job_serializes_budget(self):
  with second_ocr.research_job() as job:
   job.budget['calls']=11
   with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    out=list(pool.map(job.recognize,[digit_image()]*3))
   self.assertEqual(sum(x is not None for x in out),1)
   self.assertEqual(job.budget['calls'],12)
 def test_worker_sigkill_cleanup(self):
  with tempfile.TemporaryDirectory() as root:
   code='import os,pathlib,signal;pathlib.Path(os.environ["SECOND_OCR_JOB_ROOT"],"sensitive.png").write_bytes(b"pixels");os.kill(os.getpid(),signal.SIGKILL)'
   status=supervised_job.run([sys.executable,'-c',code],temp_parent=root)
   self.assertEqual(status,-signal.SIGKILL);self.assertEqual(list(Path(root).iterdir()),[])
 def test_supervisor_sigterm_cleanup_and_worker_death(self):
  with tempfile.TemporaryDirectory() as root:
   marker=Path(root)/'marker.json';jobs=Path(root)/'jobs';jobs.mkdir()
   code='import os,pathlib,json,time;f=pathlib.Path(os.environ["SECOND_OCR_JOB_ROOT"]);(f/"sensitive.png").write_bytes(b"pixels");pathlib.Path('+repr(str(marker))+').write_text(json.dumps([str(f),os.getpid()]));time.sleep(30)'
   runner='import supervised_job,sys;sys.exit(supervised_job.run(sys.argv[2:],temp_parent=sys.argv[1]))'
   proc=subprocess.Popen([sys.executable,'-c',runner,str(jobs),sys.executable,'-c',code],env=dict(os.environ,PYTHONPATH=str(ROOT)))
   try:
    deadline=time.monotonic()+4
    while not marker.exists() and time.monotonic()<deadline:time.sleep(.02)
    self.assertTrue(marker.exists());folder,pid=json.loads(marker.read_text())
    proc.terminate();self.assertEqual(proc.wait(timeout=3),143)
    self.assertFalse(Path(folder).exists());self.assertEqual(list(jobs.iterdir()),[])
    self.assertFalse(Path('/proc',str(pid)).exists())
   finally:
    if proc.poll() is None:proc.kill();proc.wait()


 def test_supervisor_sigkill_kills_worker_but_requires_external_directory_cleanup(self):
  # Deliberate negative test: do not claim hard-kill cleanup is implemented.
  with tempfile.TemporaryDirectory() as root:
   marker=Path(root)/'marker.json';jobs=Path(root)/'jobs';jobs.mkdir()
   code='import os,pathlib,json,time;f=pathlib.Path(os.environ["SECOND_OCR_JOB_ROOT"]);(f/"sensitive.png").write_bytes(b"pixels");pathlib.Path('+repr(str(marker))+').write_text(json.dumps([str(f),os.getpid()]));time.sleep(30)'
   runner='import supervised_job,sys;sys.exit(supervised_job.run(sys.argv[2:],temp_parent=sys.argv[1]))'
   proc=subprocess.Popen([sys.executable,'-c',runner,str(jobs),sys.executable,'-c',code],env=dict(os.environ,PYTHONPATH=str(ROOT)))
   try:
    deadline=time.monotonic()+4
    while not marker.exists() and time.monotonic()<deadline:time.sleep(.02)
    self.assertTrue(marker.exists());folder,pid=json.loads(marker.read_text())
    proc.kill();proc.wait(timeout=3)
    deadline=time.monotonic()+2
    while time.monotonic()<deadline:
     state=Path('/proc',str(pid),'stat')
     if not state.exists() or state.read_text().split()[2]=='Z':break
     time.sleep(.02)
    else:self.fail('worker survived supervisor SIGKILL')
    self.assertTrue((Path(folder)/'sensitive.png').exists())
   finally:
    if proc.poll() is None:proc.kill();proc.wait()

 def test_cleanup_failure_restores_signal_handlers(self):
  before={sig:signal.getsignal(sig) for sig in (signal.SIGTERM,signal.SIGINT)}
  real=supervised_job.shutil.rmtree
  count=[0]
  def fail_once(*args,**kwargs):
   count[0]+=1
   if count[0]==1:raise OSError('simulated cleanup failure')
   return real(*args,**kwargs)
  with tempfile.TemporaryDirectory() as root:
   with patch('supervised_job.shutil.rmtree',side_effect=fail_once):
    with self.assertRaisesRegex(OSError,'simulated cleanup failure'):
     supervised_job.run([sys.executable,'-c','pass'],temp_parent=root)
   self.assertEqual(list(Path(root).iterdir()),[])
  self.assertEqual(before,{sig:signal.getsignal(sig) for sig in before})
 def test_nonmain_supervisor_rejected_before_directory_creation(self):
  with tempfile.TemporaryDirectory() as root:
   with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
    future=pool.submit(supervised_job.run,[sys.executable,'-c','pass'],temp_parent=root)
    with self.assertRaisesRegex(RuntimeError,'main thread'):future.result()
   self.assertEqual(list(Path(root).iterdir()),[])

if __name__=='__main__':unittest.main()
