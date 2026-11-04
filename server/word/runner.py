"""One disposable Stirling container per task. No document network egress."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from preflight import inspect_docx, conversion_options, Rejected

IMAGE = 'sha256:a202357523296211bceac18fccac696470a05b9a1b5fcc98049471abb5123178'
MEMORY_MIB = 2560
# The platform is disposable after one conversion: avoid expensive top-tier JIT warmup.
# Leave memory for LibreOffice and metaspace within the container's fixed ceiling.
JAVA_OPTIONS = '-Xms256m -Xmx1280m -XX:TieredStopAtLevel=1 -XX:ActiveProcessorCount=2'

def emit(**value):
    print(json.dumps(value), flush=True)

def remove_verified(name, by_id=False):
    """An unavailable daemon is not evidence that a container is absent."""
    subprocess.run(['docker', 'rm', '-fv', name], capture_output=True, timeout=20)
    remaining = subprocess.run(
        ['docker', 'ps', '-aq', '--filter', f'id={name}' if by_id else f'name=^/{name}$'],
        check=True, capture_output=True, timeout=20)
    if remaining.stdout.strip():
        raise RuntimeError('Container cleanup could not be verified')

def run(directory):
    directory = Path(directory).resolve()
    cancel = directory / 'cancel'
    name = 'smartpdf-word-' + uuid.uuid4().hex
    preparation_name = name + '-view'
    network = os.environ.get('WORD_DOCKER_NETWORK', 'smartpdf-word')
    done = threading.Event()
    expired = threading.Event()
    started = time.monotonic()
    created = False
    preparation_created = False
    phase = 'checking'
    def docker(*args, timeout=20, input=None):
        return subprocess.run(['docker', *args], check=True, capture_output=True, timeout=timeout, input=input)
    def stop(*_):
        cancel.touch()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    def monitor():
        while not done.wait(.25):
            if cancel.exists() or time.monotonic() - started > 240:
                expired.set()
                cancel.touch()
                try:
                    docker('rm', '-fv', name)
                except Exception:
                    pass
                try: docker('rm', '-fv', preparation_name)
                except Exception: pass
                return
    watcher = threading.Thread(target=monitor, daemon=True)
    watcher.start()
    try:
        emit(state='checking')
        options_file = directory / 'options.json'
        options = conversion_options(json.loads(options_file.read_text()) if options_file.exists() else None)
        details = {}
        warnings = inspect_docx(directory / 'input.docx', options, details=details)
        emit(warnings=warnings)
        if cancel.exists():
            return
        # The network must be provisioned as internal; never create a permissive fallback.
        net = json.loads(docker('network', 'inspect', network).stdout)[0]
        if not net.get('Internal'):
            raise RuntimeError('network')
        filename = 'input.docx'
        if details['revisions'] or details['comments']:
            emit(state='preparing'); phase='preparing'
            docker('create', '--name', preparation_name, '--network', 'none', '--memory', f'{MEMORY_MIB}m', '--memory-swap', f'{MEMORY_MIB}m', '--cpus', '2',
                   '--label', 'smartpdf.word-service=word-v1', '--pids-limit', '512', '--security-opt', 'no-new-privileges', '--cap-drop', 'NET_RAW',
                   '--tmpfs', '/tmp:rw,nosuid,nodev,size=384m', '--entrypoint', 'sleep', IMAGE, 'infinity')
            preparation_created=True
            if cancel.exists(): return
            docker('start',preparation_name)
            # Stream into the running RAM filesystem. docker cp may write under
            # a tmpfs mount rather than into the filesystem Office actually sees.
            writer = 'import sys,pathlib;p=pathlib.Path(sys.argv[1]);p.write_bytes(sys.stdin.buffer.read());p.chmod(0o600)'
            docker('exec','-i',preparation_name,'python3','-c',writer,'/tmp/word-source.docx',input=(directory/filename).read_bytes())
            docker('exec','-i',preparation_name,'python3','-c',writer,'/tmp/prepare_uno.py',input=Path(__file__).with_name('prepare_uno.py').read_bytes())
            preparation=dict(options,_hasRevisions=details['revisions'])
            docker('exec',preparation_name,'python3','/tmp/prepare_uno.py','/tmp/word-source.docx','/tmp/word-prepared.docx',json.dumps(preparation),timeout=90)
            reader = 'import sys;f=open("/tmp/word-prepared.docx","rb");sys.stdout.buffer.write(f.read(30*1024**2+1))'
            prepared=docker('exec',preparation_name,'python3','-c',reader).stdout
            if len(prepared)>30*1024**2:raise RuntimeError('Prepared document exceeds limit')
            (directory/'prepared.docx').write_bytes(prepared)
            inspect_docx(directory/'prepared.docx')
            remove_verified(preparation_name);preparation_created=False
            filename='prepared.docx'
            if cancel.exists() or expired.is_set():return
        emit(state='starting')
        phase = 'starting'
        docker('create', '--name', name, '--network', network, '--memory', f'{MEMORY_MIB}m', '--memory-swap', f'{MEMORY_MIB}m', '--cpus', '2',
               '--label', 'smartpdf.word-service=word-v1',
               '--pids-limit', '512', '--security-opt', 'no-new-privileges',
               '--cap-drop', 'NET_RAW', '--tmpfs', '/tmp:rw,nosuid,nodev,size=384m',
               '-e', 'SECURITY_ENABLELOGIN=false', '-e', 'SYSTEM_DEFAULTLOCALE=en-US',
               '-e', 'TZ=UTC', '-e', 'JAVA_CUSTOM_OPTS=' + JAVA_OPTIONS,
               '-e', 'SPRING_MAIN_LAZY_INITIALIZATION=true', IMAGE)
        created = True
        if cancel.exists():
            return
        docker('start', name)
        info = json.loads(docker('inspect', name).stdout)[0]
        address = info['NetworkSettings']['Networks'][network]['IPAddress']
        base = 'http://' + address + ':8080'
        ready = False
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline and not cancel.exists() and not expired.is_set():
            try:
                with urllib.request.urlopen(base + '/api/v1/info/status', timeout=2) as response:
                    ready = response.status == 200
                if ready:
                    break
            except Exception:
                time.sleep(.5)
        if not ready:
            raise RuntimeError('startup')
        emit(state='converting')
        phase = 'converting'
        boundary = uuid.uuid4().hex
        data = (directory / filename).read_bytes()
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="fileInput"; filename="document.docx"\r\n'
                'Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document\r\n\r\n').encode() + data + f'\r\n--{boundary}--\r\n'.encode()
        request = urllib.request.Request(base + '/api/v1/convert/file/pdf', data=body,
            headers={'Content-Type': 'multipart/form-data; boundary=' + boundary}, method='POST')
        with urllib.request.urlopen(request, timeout=90) as response:
            result = response.read(30 * 1024**2 + 1)
        phase = 'checking-result'
        if len(result) > 30 * 1024**2 or not result.startswith(b'%PDF-'):
            raise RuntimeError('output')
        if cancel.exists() or expired.is_set():
            return
        (directory / 'output.pdf').write_bytes(result)
        emit(state='checking-result')
    except Rejected as error:
        emit(error=str(error), code='INPUT_REJECTED')
        return 2
    except Exception as error:
        code = 'CONVERSION_TIMEOUT' if expired.is_set() or isinstance(error, (TimeoutError, subprocess.TimeoutExpired)) else 'OUTPUT_INVALID' if phase == 'checking-result' else 'INPUT_VIEW_PREPARATION_FAILED' if phase == 'preparing' else 'ENGINE_STARTUP_FAILED' if phase == 'starting' else 'CONVERSION_FAILED'
        emit(error='Conversion could not finish. Try again or export the document from Word.', code=code)
        return 3
    finally:
        done.set()
        watcher.join(timeout=25)
        cleanup_failed = False
        for candidate, exists in ((name, created), (preparation_name, preparation_created)):
            if not exists: continue
            try: remove_verified(candidate)
            except Exception: cleanup_failed = True
        if cleanup_failed:
            # Report cleanup failure: the API must not claim success or start another task.
            emit(cleanupFailed=True)
    return 0

if __name__ == '__main__':
    if sys.argv[1] == '--reap':
        # Dedicated single-instance service: remove only our explicitly labelled orphans.
        result = subprocess.run(['docker', 'ps', '-aq', '--filter', 'label=smartpdf.word-service=word-v1'], check=True, capture_output=True, timeout=20)
        for container in result.stdout.decode().split():
            remove_verified(container, by_id=True)
    else:
        sys.exit(run(sys.argv[1]))
