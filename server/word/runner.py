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
from preflight import inspect_docx, Rejected

IMAGE = 'docker.stirlingpdf.com/stirlingtools/stirling-pdf@sha256:c6872dd056b0046a14c5de1e9970283e7f1e1ff685bb08090c6b37a231127d31'
MEMORY_MIB = 2560

def emit(**value):
    print(json.dumps(value), flush=True)

def remove_verified(name, by_id=False):
    """An unavailable daemon is not evidence that a container is absent."""
    subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=20)
    remaining = subprocess.run(
        ['docker', 'ps', '-aq', '--filter', f'id={name}' if by_id else f'name=^/{name}$'],
        check=True, capture_output=True, timeout=20)
    if remaining.stdout.strip():
        raise RuntimeError('Container cleanup could not be verified')

def run(directory):
    directory = Path(directory).resolve()
    cancel = directory / 'cancel'
    name = 'smartpdf-word-' + uuid.uuid4().hex
    network = os.environ.get('WORD_DOCKER_NETWORK', 'smartpdf-word')
    done = threading.Event()
    expired = threading.Event()
    started = time.monotonic()
    created = False
    phase = 'checking'
    def docker(*args, timeout=20):
        return subprocess.run(['docker', *args], check=True, capture_output=True, timeout=timeout)
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
                    docker('rm', '-f', name)
                except Exception:
                    pass
                return
    watcher = threading.Thread(target=monitor, daemon=True)
    watcher.start()
    try:
        emit(state='checking')
        warnings = inspect_docx(directory / 'input.docx')
        emit(warnings=warnings)
        if cancel.exists():
            return
        # The network must be provisioned as internal; never create a permissive fallback.
        net = json.loads(docker('network', 'inspect', network).stdout)[0]
        if not net.get('Internal'):
            raise RuntimeError('network')
        emit(state='starting')
        phase = 'starting'
        docker('create', '--name', name, '--network', network, '--memory', f'{MEMORY_MIB}m', '--memory-swap', f'{MEMORY_MIB}m', '--cpus', '2',
               '--label', 'smartpdf.word-service=word-v1',
               '--pids-limit', '512', '--security-opt', 'no-new-privileges',
               '--cap-drop', 'NET_RAW', '--tmpfs', '/tmp:rw,nosuid,nodev,size=384m',
               '-e', 'SECURITY_ENABLELOGIN=false', '-e', 'SYSTEM_DEFAULTLOCALE=en-US',
               '-e', 'TZ=UTC', IMAGE)
        created = True
        if cancel.exists():
            return
        docker('start', name)
        info = json.loads(docker('inspect', name).stdout)[0]
        address = info['NetworkSettings']['Networks'][network]['IPAddress']
        base = 'http://' + address + ':8080'
        ready = False
        deadline = time.monotonic() + 120
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
        data = (directory / 'input.docx').read_bytes()
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="fileInput"; filename="document.docx"\r\n'
                'Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document\r\n\r\n').encode() + data + f'\r\n--{boundary}--\r\n'.encode()
        request = urllib.request.Request(base + '/api/v1/convert/file/pdf', data=body,
            headers={'Content-Type': 'multipart/form-data; boundary=' + boundary}, method='POST')
        with urllib.request.urlopen(request, timeout=90) as response:
            result = response.read(30 * 1024**2 + 1)
        if len(result) > 30 * 1024**2 or not result.startswith(b'%PDF-'):
            raise RuntimeError('output')
        if cancel.exists() or expired.is_set():
            return
        (directory / 'output.pdf').write_bytes(result)
        emit(state='checking-result')
    except Rejected as error:
        emit(error=str(error), code='INPUT_REJECTED')
        return 2
    except Exception:
        code = 'CONVERSION_TIMEOUT' if expired.is_set() else 'ENGINE_STARTUP_FAILED' if phase == 'starting' else 'CONVERSION_FAILED'
        emit(error='Conversion could not finish. Try again or export the document from Word.', code=code)
        return 3
    finally:
        done.set()
        watcher.join(timeout=25)
        try:
            if created:
                # Monitor may already have removed it; confirm absence with a healthy daemon.
                remove_verified(name)
        except Exception:
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
