"""Read-only host preflight. Creates no containers, files, networks or cloud resources."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from urllib.parse import urlsplit
from runner import IMAGE

def command(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=25).stdout

def inspect_host(production=False):
    checks = []
    def record(name, passed, detail):
        checks.append(dict(name=name, passed=bool(passed), detail=detail))
    record('python', sys.version_info >= (3, 10), 'Python 3.10 or later required')
    record('linux', sys.platform == 'linux', 'Run on the Linux conversion host')
    if production:
        record('dedicated-linux', 'microsoft' not in platform.release().lower(), 'WSL is local development evidence only')
        record('service-user', hasattr(os, 'geteuid') and os.geteuid() != 0, 'Run as the dedicated service user')
    origin = urlsplit(os.environ.get('WORD_PUBLIC_ORIGIN', ''))
    record('origin', bool(origin.hostname) and not origin.username and not origin.password
           and origin.path == '' and not origin.query and not origin.fragment
           and (origin.scheme == 'https' if production else origin.scheme in ('http', 'https')),
           'Set an exact public HTTPS origin for production')
    label = os.environ.get('WORD_PROCESSING_LABEL', '').strip()
    record('processing-region', bool(label) and (not production or not any(s in label.lower() for s in ['development', 'example', 'not a cloud', 'localhost'])),
           'Set the verified physical processing region')
    directory = Path(os.environ.get('WORD_DATA_DIR', ''))
    configured = bool(os.environ.get('WORD_DATA_DIR')) and directory.is_absolute() and directory.is_dir()
    record('task-directory', configured, 'Explicit existing dedicated absolute task directory required')
    if configured:
        record('task-directory-access', os.access(directory, os.W_OK | os.X_OK), 'Service user must be able to write and clean tasks')
        if sys.platform == 'linux':
            record('task-directory-private', directory.stat().st_mode & 0o077 == 0, 'Task directory permissions must be 0700')
        record('task-storage-space', shutil.disk_usage(directory).free >= 2 * 1024**3, 'At least 2 GiB free task storage; verify filesystem quota separately')
    try:
        version = command('node', '--version').strip().lstrip('v').split('.')
        record('node', tuple(map(int, version[:2])) >= (24, 15), 'Node 24.15 or later required')
    except Exception:
        record('node', False, 'Node is unavailable to the service user')
    try:
        info = json.loads(command('docker', 'info', '--format', '{{json .}}'))
        record('docker-linux', info.get('OSType') == 'linux', 'Linux Docker engine required')
        record('docker-memory', info.get('MemTotal', 0) >= 3.5 * 1024**3, 'At least 3.5 GiB Docker-host memory; dedicated 4 GiB host with one conversion at a time')
        record('docker-cpu', info.get('NCPU', 0) >= 2, 'At least two CPUs required')
        image = json.loads(command('docker', 'image', 'inspect', IMAGE))[0]
        record('fixed-image', IMAGE in image.get('RepoDigests', []), 'Pinned reviewed image must already be available')
        network = json.loads(command('docker', 'network', 'inspect', os.environ.get('WORD_DOCKER_NETWORK', 'smartpdf-word')))[0]
        record('internal-network', network.get('Internal') is True, 'Conversion network must prohibit external egress')
    except Exception:
        record('docker-environment', False, 'Docker, fixed image or internal network unavailable; no automatic repair performed')
    return checks

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--production', action='store_true')
    args = parser.parse_args()
    checks = inspect_host(args.production)
    passed = all(c['passed'] for c in checks)
    print(json.dumps(dict(passed=passed, production=args.production, checks=checks)))
    sys.exit(0 if passed else 1)
