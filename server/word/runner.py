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

IMAGE = 'sha256:a202357523296211bceac18fccac696470a05b9a1b5fcc98049471abb5123178'
MEMORY_MIB = 2560
# The platform is disposable after one conversion: avoid expensive top-tier JIT warmup.
# Leave memory for LibreOffice and metaspace within the container's fixed ceiling.
JAVA_OPTIONS = '-Xms256m -Xmx1280m -XX:TieredStopAtLevel=1 -XX:ActiveProcessorCount=2'

def load_excel_preflight():
    import importlib.util
    excel_directory = Path(__file__).resolve().parents[1] / 'excel'
    sys.path.insert(0, str(excel_directory))
    spec = importlib.util.spec_from_file_location('excel_preflight', excel_directory / 'preflight.py')
    excel = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(excel)
    return excel

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

def run(directory, kind='word'):
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
        filename = 'input.docx'
        mime = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        image = IMAGE
        if kind == 'excel':
            excel = load_excel_preflight()
            try:
                warnings = excel.prepare(directory / 'input.xlsx', directory / 'prepared.xlsx', json.loads((directory / 'options.json').read_text()))
            except excel.Rejected as error:
                raise Rejected(str(error)) from None
            filename = 'prepared.xlsx'
            mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            # Separate reviewed local candidate; never change Word's runtime pin.
            image = json.loads((Path(__file__).resolve().parents[2] / 'config/excel-core.stirling-3.2.2.json').read_text())['imageId']
        else:
            warnings = inspect_docx(directory / filename)
        emit(warnings=warnings)
        if cancel.exists():
            return
        if kind == 'excel':
            # Same reviewed LibreOffice engine, without starting the Java HTTP app.
            # One fresh, disconnected container and profile for each document.
            emit(state='starting')
            phase = 'starting'
            docker('create', '--name', name, '--network', 'none',
                   '--memory', f'{MEMORY_MIB}m', '--memory-swap', f'{MEMORY_MIB}m', '--cpus', '2',
                   '--label', 'smartpdf.word-service=word-v1', '--pids-limit', '512',
                   '--security-opt', 'no-new-privileges', '--cap-drop', 'NET_RAW',
                   '--tmpfs', '/tmp:rw,nosuid,nodev,size=384m', '-e', 'TZ=UTC',
                   '-e', 'HOME=/tmp', '-e', 'XDG_CACHE_HOME=/tmp/.cache',
                   '--entrypoint', 'sleep', image, '240')
            created = True
            docker('start', name)
            if cancel.exists(): return
            # Stream into the live tmpfs as the unprivileged renderer user.
            # docker cp can write below a tmpfs mount rather than into the mounted directory.
            subprocess.run(['docker', 'exec', '-i', name, 'sh', '-c', 'umask 077; cat > /tmp/input.xlsx'],
                           input=(directory / filename).read_bytes(), check=True, capture_output=True, timeout=20)
            emit(state='converting')
            phase = 'converting'
            docker('exec', name, 'libreoffice', '--headless',
                   '-env:UserInstallation=file:///tmp/excel-profile',
                   '--convert-to', 'pdf:calc_pdf_Export', '--outdir', '/tmp', '/tmp/input.xlsx', timeout=90)
            size = int(docker('exec', name, 'stat', '-c', '%s', '/tmp/input.pdf').stdout)
            if not 0 < size <= 30 * 1024**2: raise RuntimeError('output')
            if cancel.exists() or expired.is_set(): return
            result = docker('exec', name, 'cat', '/tmp/input.pdf').stdout
            if len(result) != size or not result.startswith(b'%PDF-'): raise RuntimeError('output')
            (directory / 'output.pdf').write_bytes(result)
            emit(state='checking-result')
            return 0
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
               '-e', 'TZ=UTC', '-e', 'JAVA_CUSTOM_OPTS=' + JAVA_OPTIONS,
               '-e', 'SPRING_MAIN_LAZY_INITIALIZATION=true', image)
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
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="fileInput"; filename="{filename}"\r\n'
                f'Content-Type: {mime}\r\n\r\n').encode() + data
        if kind == 'excel':
            # 3.2.2 otherwise may choose the in-process converter, which drops charts.
            # Pin the Excel rendering path explicitly; leave Word's approved path alone.
            body += (f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="useStirlingOfficeConvert"\r\n\r\nfalse').encode()
        body += f'\r\n--{boundary}--\r\n'.encode()
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
        sys.exit(run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else 'word'))
