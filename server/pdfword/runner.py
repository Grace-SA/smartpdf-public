"""Disposable offline PDF-to-Word task. Never mount a user directory into Docker."""
import json
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
class Rejected(ValueError):
    pass

IMAGE = json.loads((Path(__file__).resolve().parents[2] / 'config/pdfword-runtime.json').read_text())['imageId']


def emit(**value):
    print(json.dumps(value), flush=True)


def run(directory):
    directory = Path(directory).resolve()
    cancel = directory / 'cancel'
    name = 'smartpdf-pdfword-' + uuid.uuid4().hex
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
        if not 0 < (directory / 'input.pdf').stat().st_size <= 30 * 1024**2:
            raise Rejected('Choose a PDF under 30 MiB.')
        if cancel.exists():
            return 0
        emit(state='starting')
        docker('create', '--name', name, '--network', 'none', '--memory', '768m', '--memory-swap', '768m',
               '--cpus', '1', '--pids-limit', '64', '--security-opt', 'no-new-privileges', '--cap-drop', 'ALL',
               '--read-only', '--tmpfs', '/tmp:rw,nosuid,nodev,size=160m', '--user', '10001:10001',
               '--label', 'smartpdf.pdfword-service=pdfword-v1', '--entrypoint', 'sleep', IMAGE, 'infinity')
        created = True
        if cancel.exists():
            return 0
        docker('start', name)
        writer = 'import sys,pathlib;p=pathlib.Path(sys.argv[1]);p.write_bytes(sys.stdin.buffer.read());p.chmod(0o600)'
        for source, destination in ((directory / 'input.pdf', '/tmp/input.pdf'),
                                    (Path(__file__).with_name('legacy_worker.py'), '/tmp/worker.py')):
            docker('exec', '-i', name, 'python3', '-c', writer, destination, input=source.read_bytes())
        if cancel.exists():
            return 0
        emit(state='converting')
        try:
            output = docker('exec', '-e', 'HOME=/tmp', name, 'python3', '/tmp/worker.py', '/tmp/input.pdf', '/tmp/output.docx', timeout=90)
        except subprocess.CalledProcessError as error:
            try:
                report = json.loads(error.stdout)
                if report.get('code') == 'INPUT_REJECTED':
                    raise Rejected(report['error'])
            except (ValueError, KeyError) as parse_error:
                if isinstance(parse_error, Rejected):
                    raise
            raise RuntimeError('Conversion failed') from error
        reported = json.loads(output.stdout)
        if not isinstance(reported.get('pages'), int) or not 1 <= reported['pages'] <= 200:
            raise RuntimeError('Invalid page count')
        emit(state='checking-result')
        reader = 'import sys;sys.stdout.buffer.write(open("/tmp/output.docx","rb").read(30*1024**2+1))'
        result = docker('exec', name, 'python3', '-c', reader).stdout
        if not result.startswith(b'PK') or len(result) > 30 * 1024**2:
            raise RuntimeError('Invalid output')
        if not cancel.exists():
            (directory / 'expected.json').write_text(json.dumps({'pages': reported['pages']}))
            (directory / 'output.docx').write_bytes(result)
        return 0
    except Rejected as error:
        emit(error=str(error), code='INPUT_REJECTED')
        return 2
    except Exception:
        emit(error='Conversion could not finish. Retry or choose a simpler PDF.', code='CONVERSION_TIMEOUT' if timed_out else 'CONVERSION_FAILED')
        return 3
    finally:
        done.set()
        watcher.join(timeout=25)
        if created:
            try:
                if docker('ps', '-aq', '--filter', 'name=^/' + name + '$').stdout.strip():
                    docker('rm', '-fv', name)
                if docker('ps', '-aq', '--filter', 'name=^/' + name + '$').stdout.strip():
                    raise RuntimeError('cleanup')
            except Exception:
                emit(cleanupFailed=True)


if __name__ == '__main__':
    if sys.argv[1] == '--reap':
        result = subprocess.run(['docker', 'ps', '-aq', '--filter', 'label=smartpdf.pdfword-service=pdfword-v1'], check=True, capture_output=True, timeout=20)
        for identifier in result.stdout.decode().split():
            subprocess.run(['docker', 'rm', '-fv', identifier], check=True, capture_output=True, timeout=20)
        sys.exit(0)
    sys.exit(run(sys.argv[1]))
