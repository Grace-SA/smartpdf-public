"""Read only the font files advertised by fontconfig in the pinned image."""
import hashlib
import json
from pathlib import Path
import subprocess

files = subprocess.run(['fc-list', '--format', '%{file}\n'], capture_output=True, check=True).stdout.decode().splitlines()
fonts = []
for name in sorted(set(files)):
    path = Path(name)
    fonts.append({'path': name, 'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
print(json.dumps({'profile': 'stirling-3.2.2-builtin-v1', 'fonts': fonts}, indent=2))
