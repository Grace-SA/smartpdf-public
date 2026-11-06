"""PPT adapter in a pinned Stirling open-source core container, with no network."""
import json
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from preflight import inspect_pptx, Rejected

IMAGE = json.loads((Path(__file__).resolve().parents[2] / 'config/ppt-core.stirling-3.2.2.json').read_text())['imageId']


def emit(**value):
    print(json.dumps(value), flush=True)


def run(directory):
    directory = Path(directory).resolve()
    cancel = directory / 'cancel'
    name = 'smartpdf-ppt-' + uuid.uuid4().hex
    done = threading.Event()
    created = False
    timed_out = False

    def docker(*args, timeout=20, input=None):
        return subprocess.run(['docker', *args], check=True, capture_output=True, timeout=timeout, input=input)

    def stop(*_):
        cancel.touch()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    def watch():
        nonlocal timed_out
        started = time.monotonic()
        while not done.wait(.25):
            if cancel.exists() or time.monotonic() - started > 120:
                timed_out = not cancel.exists()
                cancel.touch()
                try:
                    docker('rm', '-fv', name)
                except Exception:
                    pass
                return

    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    try:
        emit(state='checking')
        details = inspect_pptx(directory / 'input.pptx')
        emit(warnings=details['warnings'])
        if cancel.exists():
            return 0
        emit(state='starting')
        created = True
        docker('create', '--name', name, '--network', 'none', '--memory', '2560m', '--memory-swap', '2560m',
               '--cpus', '2', '--pids-limit', '512', '--security-opt', 'no-new-privileges', '--cap-drop', 'ALL',
               '--read-only', '--tmpfs', '/tmp:rw,nosuid,nodev,size=512m', '--user', '1000:1000',
               '--label', 'smartpdf.ppt-service=ppt-v1', '--entrypoint', 'sleep', IMAGE, 'infinity')
        if cancel.exists():
            return 0
        docker('start', name)
        writer = 'import sys,pathlib;p=pathlib.Path(sys.argv[1]);p.write_bytes(sys.stdin.buffer.read());p.chmod(0o600)'
        for source, destination in ((directory / 'input.pptx', '/tmp/input.pptx'),
                                    (Path(__file__).with_name('layout.py'), '/tmp/layout.py'),
                                    (Path(__file__).with_name('export_uno.py'), '/tmp/export_uno.py')):
            docker('exec', '-i', name, 'python3', '-c', writer, destination, input=source.read_bytes())
        if cancel.exists():
            return 0
        emit(state='converting')
        output = docker('exec', '-e', 'HOME=/tmp', name, 'python3', '/tmp/export_uno.py', '/tmp/input.pptx', '/tmp/output.pdf', timeout=90)
        reported = json.loads(output.stdout)
        if reported['visible'] != details['visible']:
            raise RuntimeError('Slide scope differs')
        emit(state='checking-result')
        # Independent PDF parser and renderer tools, not the Office export API.
        info = docker('exec', name, 'pdfinfo', '/tmp/output.pdf').stdout.decode()
        import re
        if int(re.search(r'^Pages:\s+(\d+)', info, re.M)[1]) != details['visible']:
            raise RuntimeError('Page count differs')
        width, height = map(float, re.search(r'^Page size:\s+([\d.]+) x ([\d.]+)', info, re.M).groups())
        if abs(width - details['width']) > .1 or abs(height - details['height']) > .1:
            raise RuntimeError('Page size differs')
        reader = 'import sys;sys.stdout.buffer.write(open("/tmp/output.pdf","rb").read(30*1024**2+1))'
        result = docker('exec', name, 'python3', '-c', reader).stdout
        if not result.startswith(b'%PDF-') or len(result) > 30 * 1024**2:
            raise RuntimeError('Invalid output')
        if not cancel.exists():
            (directory / 'expected.json').write_text(json.dumps({key: details[key] for key in ('visible', 'width', 'height')}))
            (directory / 'output.pdf').write_bytes(result)
        return 0
    except Rejected as error:
        emit(error=str(error), code='INPUT_REJECTED')
        return 2
    except Exception:
        emit(error='Conversion could not finish. Try again or export from PowerPoint.', code='CONVERSION_TIMEOUT' if timed_out else 'CONVERSION_FAILED')
        return 3
    finally:
        done.set()
        watcher.join(timeout=25)
        if created:
            try:
                docker('rm', '-fv', name)
                if docker('ps', '-aq', '--filter', 'name=^/' + name + '$').stdout.strip():
                    raise RuntimeError('cleanup')
            except Exception:
                emit(cleanupFailed=True)


if __name__ == '__main__':
    if sys.argv[1] == '--reap':
        result = subprocess.run(['docker', 'ps', '-aq', '--filter', 'label=smartpdf.ppt-service=ppt-v1'], check=True, capture_output=True, timeout=20)
        for identifier in result.stdout.decode().split():
            subprocess.run(['docker', 'rm', '-fv', identifier], check=True, capture_output=True, timeout=20)
        sys.exit(0)
    sys.exit(run(sys.argv[1]))
