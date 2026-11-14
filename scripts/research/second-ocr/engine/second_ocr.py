"""ISOLATED RESEARCH ONLY: checksum-locked, resource-bounded second reader."""
import math,csv,hashlib,io,json,os,subprocess,sys,tempfile,time,threading,fcntl
from contextvars import ContextVar
from contextlib import contextmanager, ExitStack
from pathlib import Path
import cv2

ROOT=Path(__file__).resolve().parents[1]
LOCK=ROOT/'engine-lock.json'
_current = ContextVar('second_ocr_job', default=None)

class Job:
    """Explicit research-only job; serialize calls to enforce aggregate limits."""
    def __init__(self, folder, lock_path):
        self.folder = folder
        self.lock_path = Path(lock_path)
        self.budget = {'calls': 0, 'seconds': 0.0}
        self.verified = None
        self.measurements = []
        self.closed = False
        self.mutex = threading.Lock()

    def recognize(self, crop):
        with self.mutex:
            if self.closed:
                return None
            return self._recognize(crop)

    def _recognize(self, crop):
        if crop.ndim!=3 or crop.shape[0]*crop.shape[1]>16384 or self.budget['calls']>=12 or self.budget['seconds']>=8:
            return None
        try:
            if self.verified is None:
                c=json.loads(self.lock_path.read_text())
                if any(hashlib.sha256(Path(c[k]).read_bytes()).hexdigest()!=c['sha256'][k] for k in ('binary','library','model')):
                    return None
                self.verified=c
            # Linux anonymous FDs: no crop/config/result pathname survives SIGKILL.
            if sys.platform != 'linux' or not hasattr(os, 'memfd_create'):
                return None
            ok, encoded = cv2.imencode('.png', cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))
            if not ok or encoded.nbytes > 65536:
                return None
            with ExitStack() as stack:
                def anonymous(name, payload=None):
                    fd = os.memfd_create(name, os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
                    stack.callback(os.close, fd)
                    if payload is not None:
                        with os.fdopen(os.dup(fd), 'wb') as target:
                            target.write(payload)
                        os.lseek(fd, 0, os.SEEK_SET)
                        # Linux UAPI values from linux/fcntl.h; some Python builds omit names.
                        fcntl.fcntl(fd, getattr(fcntl, 'F_ADD_SEALS', 1033), 0x000F)
                    return fd
                config_fd = anonymous('ocr-config', json.dumps(self.verified).encode())
                input_fd = anonymous('ocr-input', encoded.tobytes())
                output_fd = anonymous('ocr-output')
                before=time.monotonic();self.budget['calls']+=1
                try:
                    r=subprocess.run([sys.executable,str(ROOT/'limited_tesseract.py'),
                        '/proc/self/fd/'+str(config_fd), '/proc/self/fd/'+str(input_fd)],
                        pass_fds=(config_fd,input_fd),stdout=output_fd,stderr=subprocess.DEVNULL,
                        timeout=min(2,8-self.budget['seconds']),check=False)
                except subprocess.TimeoutExpired:
                    self.budget['seconds']+=time.monotonic()-before;return None
                elapsed=time.monotonic()-before;self.budget['seconds']+=elapsed
                self.measurements.append({'seconds':elapsed,'returncode':r.returncode,'pixels':crop.shape[0]*crop.shape[1]})
                if r.returncode or os.fstat(output_fd).st_size>65536:return None
                os.lseek(output_fd,0,os.SEEK_SET)
                data=os.read(output_fd,65537)
                parsed=csv.DictReader(io.StringIO(data.decode('utf8')),delimiter='\t')
                if parsed.fieldnames!=['level','page_num','block_num','par_num','line_num','word_num','left','top','width','height','conf','text']:return None
                rows=list(parsed)
                if len(rows)>64:return None
                words=[]
                for v in rows:
                    if set(v) != set(parsed.fieldnames) or any(not isinstance(value,str) for value in v.values()):
                        return None
                    if not v['text'].strip():continue
                    if v.get('level')!='5' or None in v:return None
                    score=float(v['conf']);left,top,width,height=(int(v[k])for k in ('left','top','width','height'))
                    if not math.isfinite(score) or not 0<=score<=100 or not (0<=left<left+width<=crop.shape[1] and 0<=top<top+height<=crop.shape[0]):return None
                    words.append((v['text'],score))
                return words
        except (OSError,ValueError,KeyError,UnicodeError,TypeError):
            return None

@contextmanager
def research_job(*, temp_parent=None, lock_path=None):
    # Caller explicitly opts in. No process-global default job or model cache.
    with tempfile.TemporaryDirectory(prefix='second-ocr-job-', dir=temp_parent) as folder:
        job = Job(folder, LOCK if lock_path is None else lock_path)
        token = _current.set(job)
        try:
            yield job
        finally:
            with job.mutex:
                job.closed = True
                job.verified = None
            _current.reset(token)

def recognize(crop):
    job = _current.get()
    return None if job is None else job.recognize(crop)

def enabled():
    job = _current.get()
    return job is not None and not job.closed
