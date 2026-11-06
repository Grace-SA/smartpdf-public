"""Verify the pinned local PPT environment. Never promotes a new image implicitly."""
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
config = json.loads((root / 'config/ppt-core.stirling-3.2.2.json').read_text())


def identity(name):
    return subprocess.run(['docker', 'image', 'inspect', name, '--format', '{{.Id}}'],
                          check=True, capture_output=True, text=True, timeout=20).stdout.strip()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--production', action='store_true')
    args = parser.parse_args()
    if not args.production and identity(config['baselineTag']) != config['baselineImageId']:
        raise SystemExit('The baseline tag does not match the reviewed core image.')
    if identity(config['imageId']) != config['imageId']:
        raise SystemExit('The PPT image does not match its approved local pin.')
    if hashlib.sha256((root / 'server/ppt/Dockerfile').read_bytes()).hexdigest() != config['dockerfileSha256']:
        raise SystemExit('The PPT build recipe differs from the reviewed provenance.')
    if args.production:
        origin = urlsplit(os.environ.get('PPT_PUBLIC_ORIGIN', ''))
        directory = Path(os.environ.get('PPT_DATA_DIR', ''))
        if (sys.platform != 'linux' or 'microsoft' in platform.release().lower() or os.geteuid() == 0
                or os.environ.get('OFFICE_SHARED_MODE') != 'true'):
            raise SystemExit('Production PPT requires the non-root shared Office service on Linux.')
        if (origin.scheme != 'https' or not origin.hostname or origin.username or origin.password
                or origin.path or origin.query or origin.fragment):
            raise SystemExit('Set an exact public HTTPS PPT origin.')
        if (not os.environ.get('PPT_DATA_DIR') or not directory.is_absolute() or not directory.is_dir()
                or directory.stat().st_mode & 0o077 or not os.access(directory, os.W_OK | os.X_OK)
                or shutil.disk_usage(directory).free < 4 * 1024**3):
            raise SystemExit('Set an existing private writable PPT task directory with 4 GiB free storage.')
    print('PPT baseline and candidate image identities verified. Production promotion is separate.')
