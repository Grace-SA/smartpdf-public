"""Linux-native synthetic resource probes, not deployment/container acceptance.

Limits apply only inside spawned test children after Torch has warmed up.
No limit is changed in the parent, no PDFs or model weights are used.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import unittest

ROOT = str(Path(__file__).parent.resolve())
WORKER = r'''
import ctypes, json, os, resource, sys
# Child-only: prevent ordinary core files and Linux piped core collectors.
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
libc = ctypes.CDLL(None, use_errno=True)
if libc.prctl(4, 0, 0, 0, 0) != 0 or libc.prctl(3, 0, 0, 0, 0) != 0:
    raise RuntimeError('Could not disable Linux process dumpability')
sys.path.insert(0, sys.argv[1])
import torch
from torch import nn
from cached_attention import CachedAttention, bits_equal
from budget import CacheBudget

torch.set_num_threads(1)
torch.manual_seed(int(sys.argv[3]))
q = torch.randn(1, 1, 32)
k = torch.randn(31, 1, 32)
m = nn.MultiheadAttention(32, 4).eval()
b = CacheBudget(40000)
c = CachedAttention(m, budget=b)
with torch.no_grad():
    expected = m(q, k, k, need_weights=False)[0]
    assert bits_equal(c(q, k, k, need_weights=False)[0], expected)
assert 0 < b.used <= b.limit
mode = sys.argv[2]
if mode == 'memory':
    # AS bounds virtual mappings, NOT RSS. Warm up before imposing the limit.
    pages = int(open('/proc/self/statm').read().split()[0])
    limit = pages * os.sysconf('SC_PAGE_SIZE') + 64 * 1024 * 1024
    old = resource.getrlimit(resource.RLIMIT_AS)
    if old[1] != resource.RLIM_INFINITY and old[1] < limit:
        raise RuntimeError('Existing hard AS limit too low for this probe')
    resource.setrlimit(resource.RLIMIT_AS, (limit, old[1]))
    failed = False
    try:
        oversized = torch.empty(256 * 1024 * 1024, dtype=torch.uint8)
    except (RuntimeError, MemoryError):
        failed = True
    assert failed, 'Expected bounded allocation to fail'
    with torch.no_grad():
        for _ in range(10):
            assert bits_equal(c(q, k, k, need_weights=False)[0], expected)
    c.clear()
    assert b.used == 0
    print(json.dumps({'mode': mode, 'allocation_failed': failed,
                      'subsequent_exact_calls': 10, 'live_cache_bytes': b.used}), flush=True)
elif mode == 'cpu':
    usage = resource.getrusage(resource.RUSAGE_SELF)
    soft = int(usage.ru_utime + usage.ru_stime) + 1
    hard = soft + 1
    old = resource.getrlimit(resource.RLIMIT_CPU)
    if old[1] != resource.RLIM_INFINITY and old[1] < hard:
        raise RuntimeError('Existing hard CPU limit too low for this probe')
    resource.setrlimit(resource.RLIMIT_CPU, (soft, hard))
    signal = __import__('signal')
    signal.signal(signal.SIGXCPU, signal.SIG_DFL)
    print('READY', flush=True)
    with torch.no_grad():
        while True:
            c(q, k, k, need_weights=False)
else:
    print('READY', flush=True)
    assert sys.stdin.readline() == 'GO\n'
    with torch.no_grad():
        for i in range(100):
            # Exercise replacements, not just a single immutable cache hit.
            k.add_(0.001)
            got = c(q, k, k, need_weights=False)[0]
            assert bits_equal(got, m(q, k, k, need_weights=False)[0])
            assert 0 < b.used <= b.limit
    peak = b.peak
    c.clear()
    assert b.used == 0
    print(json.dumps({'mode': mode, 'seed': int(sys.argv[3]), 'exact_calls': 100,
                      'peak_cache_bytes': peak, 'live_cache_bytes': b.used}), flush=True)
'''

@unittest.skipUnless(sys.platform == 'linux' and Path('/proc/self/statm').exists(),
                     'Linux /proc and POSIX resource limits required')
class NativeLimitsTest(unittest.TestCase):
    def setUp(self):
        self.children = []

    @contextmanager
    def directory(self):
        with tempfile.TemporaryDirectory() as directory:
            try:
                yield directory
            finally:
                # Reap before deleting the working directory, including failures.
                for child in self.children:
                    self.reap(child)
                self.children.clear()

    def spawn(self, directory, mode, seed=1):
        child = subprocess.Popen(
            [sys.executable, '-c', WORKER, ROOT, mode, str(seed)], cwd=directory,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1'),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True)
        self.children.append(child)
        return child

    @staticmethod
    def reap(child):
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=10)
        for stream in (child.stdin, child.stdout, child.stderr):
            stream.close()

    def ready(self, child):
        self.assertTrue(select.select([child.stdout], [], [], 30)[0], 'readiness timeout')
        self.assertEqual(child.stdout.readline(), b'READY\n')

    def test_two_processes_replace_and_release_independent_caches(self):
        with self.directory() as directory:
            children = [self.spawn(directory, 'parallel', seed) for seed in (11, 29)]
            for child in children:
                self.ready(child)
            # Both children own live caches before either can start its loop.
            for child in children:
                child.stdin.write(b'GO\n'); child.stdin.flush()
            for child, seed in zip(children, (11, 29)):
                out, err = child.communicate(timeout=30)
                self.assertEqual(child.returncode, 0, err.decode())
                result = json.loads(out)
                self.assertEqual(result['seed'], seed)
                self.assertEqual(result['exact_calls'], 100)
                self.assertGreater(result['peak_cache_bytes'], 0)
                self.assertLessEqual(result['peak_cache_bytes'], 40000)
                self.assertEqual(result['live_cache_bytes'], 0)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_native_address_limit_failure_does_not_poison_cache(self):
        with self.directory() as directory:
            child = self.spawn(directory, 'memory')
            out, err = child.communicate(timeout=30)
            self.assertEqual(child.returncode, 0, err.decode())
            result = json.loads(out)
            self.assertTrue(result['allocation_failed'])
            self.assertEqual(result['subsequent_exact_calls'], 10)
            self.assertEqual(result['live_cache_bytes'], 0)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_cpu_limit_terminates_and_reaps_live_cache(self):
        with self.directory() as directory:
            child = self.spawn(directory, 'cpu')
            self.ready(child)
            _, err = child.communicate(timeout=15)
            self.assertEqual(child.returncode, -signal.SIGXCPU, err.decode())
            self.assertEqual(list(Path(directory).iterdir()), [])

if __name__ == '__main__':
    unittest.main()
