"""Research supervisor: cleanup after worker crash/cancellation, not host loss.

No deployment entry point is changed. A hard-killed supervisor cannot run finally;
its private directory needs a separately owned lifecycle before production use.
"""
import ctypes
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import shutil


def worker():
    expected = int(sys.argv[2])
    if os.getppid() != expected:
        raise SystemExit(125)
    if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL, 0, 0, 0):
        raise SystemExit(125)
    if os.getppid() != expected:
        raise SystemExit(125)
    os.execv(sys.argv[3], sys.argv[3:])


def run(command, *, temp_parent=None, timeout=180):
    """Caller supplies trusted executable/arguments, never source-PDF instructions."""
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("Research supervisor requires the main thread")
    with tempfile.TemporaryDirectory(prefix='second-ocr-supervisor-', dir=temp_parent) as folder:
        env = dict(os.environ, SECOND_OCR_JOB_ROOT=folder)
        child = None
        old_handlers = {}
        def cancel(signum, frame):
            raise SystemExit(128 + signum)
        try:
            for sig in (signal.SIGTERM, signal.SIGINT):
                old_handlers[sig] = signal.signal(sig, cancel)
            child = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), '--worker', str(os.getpid()), *command],
                env=env, start_new_session=True,
            )
            return child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return 124
        finally:
            # Ignore repeat cancellation until child group is dead and files removed.
            for sig in old_handlers:
                signal.signal(sig, signal.SIG_IGN)
            try:
                if child is not None:
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    child.wait()
                # Cleanup errors propagate; never claim successful deletion on error.
                shutil.rmtree(folder)
            finally:
                for sig, handler in old_handlers.items():
                    signal.signal(sig, handler)



if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--worker':
        worker()
    else:
        raise SystemExit(run(sys.argv[1:]))
