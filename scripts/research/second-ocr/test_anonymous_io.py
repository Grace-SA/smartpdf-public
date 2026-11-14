import hashlib,json,os,signal,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'engine'));sys.path.insert(0,str(ROOT))
import second_ocr
from digit_fixture import digit_image

class AnonymousIO(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.jobs=self.root/'jobs';self.jobs.mkdir()
 def fake(self,code):
  binary=self.root/'reader.py';binary.write_text('#!/usr/bin/python3\n'+code);binary.chmod(0o700)
  c=json.loads(second_ocr.LOCK.read_text());c['binary']=str(binary);c['sha256']['binary']=hashlib.sha256(binary.read_bytes()).hexdigest()
  lock=self.root/'lock.json';lock.write_text(json.dumps(c));return lock
 def test_real_cross_process_reads_anonymous_input_without_named_artifacts(self):
  with second_ocr.research_job(temp_parent=self.jobs) as job:
   self.assertEqual(second_ocr.recognize(digit_image())[0][0],'3')
   self.assertEqual(list(Path(job.folder).iterdir()),[])
  self.assertEqual(list(self.jobs.iterdir()),[])
 def test_input_is_sealed_across_exec(self):
  marker=self.root/'sealed.json'
  lock=self.fake('import os,sys,json,fcntl\np=sys.argv[1]\nfd=os.open(p,os.O_RDWR)\nseals=fcntl.fcntl(fd,1034)\nblocked=[]\nfor action in [lambda:os.write(fd,b"x"),lambda:os.ftruncate(fd,0)]:\n try:action();blocked.append(False)\n except PermissionError:blocked.append(True)\nopen('+repr(str(marker))+',"w").write(json.dumps([seals,blocked]))\n')
  with second_ocr.research_job(temp_parent=self.jobs,lock_path=lock):
   self.assertIsNone(second_ocr.recognize(digit_image()))
  self.assertEqual(json.loads(marker.read_text()),[15,[True,True]])
 def test_fd_cleanup_on_success_and_creation_failure(self):
  count=lambda:len(list(Path('/proc/self/fd').iterdir()))
  before=count()
  for _ in range(3):
   with second_ocr.research_job(temp_parent=self.jobs):self.assertIsNotNone(second_ocr.recognize(digit_image()))
  self.assertEqual(count(),before)
  real=os.memfd_create;n=[0]
  def fail_second(*a,**kw):
   n[0]+=1
   if n[0]==2:raise OSError('simulated unavailable memory fd')
   return real(*a,**kw)
  with second_ocr.research_job(temp_parent=self.jobs),patch('second_ocr.os.memfd_create',side_effect=fail_second):
   self.assertIsNone(second_ocr.recognize(digit_image()))
  self.assertEqual(count(),before);self.assertEqual(list(self.jobs.iterdir()),[])
 def test_sigkill_has_no_named_crop_or_result_residue(self):
  marker=self.root/'active.json'
  lock=self.fake('import os,sys,json,time\nraw=open(sys.argv[1],"rb").read()\nassert raw.startswith(b"\\x89PNG")\nfds={x:os.readlink("/proc/self/fd/"+x) for x in os.listdir("/proc/self/fd") if os.path.exists("/proc/self/fd/"+x)}\nopen('+repr(str(marker))+',"w").write(json.dumps([os.getpid(),fds]))\ntime.sleep(30)\n')
  code='import sys;from second_ocr import research_job,recognize;from digit_fixture import digit_image\nwith research_job(temp_parent=sys.argv[1],lock_path=sys.argv[2]): recognize(digit_image())'
  env=dict(os.environ,PYTHONPATH=os.pathsep.join([str(ROOT/'engine'),str(ROOT)]))
  parent=subprocess.Popen([sys.executable,'-c',code,str(self.jobs),str(lock)],env=env,start_new_session=True)
  try:
   deadline=time.monotonic()+4
   while not marker.exists() and time.monotonic()<deadline:time.sleep(.01)
   self.assertTrue(marker.exists());pid,fds=json.loads(marker.read_text())
   self.assertTrue(any('memfd:ocr-input' in v for v in fds.values()))
   self.assertTrue(any('memfd:ocr-output' in v for v in fds.values()))
   self.assertEqual([p for p in self.jobs.rglob('*') if p.is_file()],[])
   parent.kill();parent.wait(timeout=2)
   deadline=time.monotonic()+2
   while time.monotonic()<deadline:
    stat=Path('/proc',str(pid),'stat')
    if not stat.exists() or stat.read_text().split()[2]=='Z':break
    time.sleep(.01)
   else:self.fail('secondary child survived parent kill')
   self.assertEqual([p for p in self.jobs.rglob('*') if p.is_file()],[])
  finally:
   try:os.killpg(parent.pid,signal.SIGKILL)
   except ProcessLookupError:pass
   parent.wait()

 def test_truncated_or_extra_tsv_fields_decline_without_exception(self):
  header='level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n'
  for row in ['5\n','5\t1\t1\t1\t1\t1\t1\t1\t1\t1\t99\t3\textra\n']:
   lock=self.fake('import sys\nsys.stdout.write('+repr(header+row)+')\n')
   with second_ocr.research_job(temp_parent=self.jobs,lock_path=lock):
    self.assertIsNone(second_ocr.recognize(digit_image()))
   self.assertEqual(list(self.jobs.iterdir()),[])

if __name__=='__main__':unittest.main()
