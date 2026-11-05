"""Verify the pinned local PPT environment. Never promotes a new image implicitly."""
import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[2]
config = json.loads((root / 'config/ppt-core.stirling-3.2.2.json').read_text())


def identity(name):
    return subprocess.run(['docker', 'image', 'inspect', name, '--format', '{{.Id}}'],
                          check=True, capture_output=True, text=True, timeout=20).stdout.strip()


if __name__ == '__main__':
    if identity(config['baselineTag']) != config['baselineImageId']:
        raise SystemExit('The baseline tag does not match the reviewed core image.')
    if identity(config['imageId']) != config['imageId']:
        raise SystemExit('The PPT image does not match its approved local pin.')
    print('PPT baseline and candidate image identities verified. Production promotion is separate.')
