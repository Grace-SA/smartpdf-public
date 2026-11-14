"""Native process cleanup only. This is not a container/cgroup test."""
import os,select,signal,subprocess,sys,tempfile,unittest
from pathlib import Path
@unittest.skipUnless(os.name=='posix','POSIX signals required')
class ProcessTest(unittest.TestCase):
    def test_sigkill_reaps_memory_only_cache(self):
        root=str(Path(__file__).parent.resolve())
        program='''import sys,time,torch
sys.path.insert(0,sys.argv[1])
from cached_attention import CachedAttention
from budget import CacheBudget
from torch import nn
torch.set_num_threads(2)
b=CacheBudget(1024*1024);m=nn.MultiheadAttention(32,4).eval();c=CachedAttention(m,budget=b)
with torch.no_grad():
 q=torch.randn(1,1,32);k=torch.randn(31,1,32);c(q,k,k,need_weights=False)
assert 0<b.used<=b.limit
print('READY',flush=True)
time.sleep(60)
'''
        with tempfile.TemporaryDirectory()as directory:
            env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='2')
            child=subprocess.Popen([sys.executable,'-c',program,root],cwd=directory,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
            try:
                self.assertTrue(select.select([child.stdout],[],[],15)[0],'Worker readiness timeout')
                self.assertEqual(child.stdout.readline(),b'READY\n')
                os.killpg(child.pid,signal.SIGKILL);self.assertEqual(child.wait(timeout=10),-signal.SIGKILL)
                self.assertEqual(list(Path(directory).iterdir()),[])
            finally:
                if child.poll()is None:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=10)
                child.stdout.close();child.stderr.close()
if __name__=='__main__':unittest.main()
