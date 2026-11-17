"""Verify the pinned local PDFWORD environment. Never promotes a new image implicitly."""
import json
import subprocess
import argparse
import hashlib
import os
import platform
import shutil
import sys
from urllib.parse import urlsplit
from pathlib import Path

root = Path(__file__).resolve().parents[2]
config = json.loads((root / 'config/pdfword-runtime.json').read_text())


def identity(name):
    return subprocess.run(['docker', 'image', 'inspect', name, '--format', '{{.Id}}'],
                          check=True, capture_output=True, text=True, timeout=20).stdout.strip()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--production', action='store_true')
    args = parser.parse_args()
    if identity(config['imageId']) != config['imageId']:
        raise SystemExit('The PDFWORD image does not match its approved local pin.')
    if hashlib.sha256((root / 'server/pdfword/Dockerfile').read_bytes()).hexdigest() != config['dockerfileSha256']:
        raise SystemExit('The PDFWORD build recipe differs from the reviewed provenance.')
    if hashlib.sha256((root / 'server/pdfword/requirements.txt').read_bytes()).hexdigest() != config['requirementsSha256']:
        raise SystemExit('The PDFWORD dependencies differ from the reviewed provenance.')
    if args.production:
        origin = urlsplit(os.environ.get('PDFWORD_PUBLIC_ORIGIN', ''))
        directory = Path(os.environ.get('PDFWORD_DATA_DIR', ''))
        if (sys.platform != 'linux' or 'microsoft' in platform.release().lower() or os.geteuid() == 0
                or os.environ.get('OFFICE_SHARED_MODE') != 'true'):
            raise SystemExit('Production PDFWORD requires the non-root shared Office service on Linux.')
        if (origin.scheme != 'https' or not origin.hostname or origin.username or origin.password
                or origin.path or origin.query or origin.fragment):
            raise SystemExit('Set an exact public HTTPS PDFWORD origin.')
        if (not os.environ.get('PDFWORD_DATA_DIR') or not directory.is_absolute() or not directory.is_dir()
                or directory.stat().st_mode & 0o077 or not os.access(directory, os.W_OK | os.X_OK)
                or shutil.disk_usage(directory).free < 4 * 1024**3):
            raise SystemExit('Set an existing private writable PDFWORD task directory with 4 GiB free storage.')
    print('PDFWORD baseline and candidate image identities verified. Production promotion is separate.')
