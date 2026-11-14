"""Opt-in download and extraction of SHA256-pinned official Debian packages."""
import argparse,hashlib,json,subprocess,urllib.request
from pathlib import Path
R=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--download',action='store_true');a=p.parse_args()
if not a.download:p.error('Explicit --download required; no package installation occurs')
root=R/'root';root.mkdir(exist_ok=True)
for item in json.loads((R/'selected-packages.json').read_text()):
 url='https://deb.debian.org/debian/'+item['Filename'];target=R/Path(item['Filename']).name
 if not target.exists():
  with urllib.request.urlopen(url,timeout=60) as response:data=response.read(int(item['Size'])+1)
 else:data=target.read_bytes()
 if len(data)!=int(item['Size']) or hashlib.sha256(data).hexdigest()!=item['SHA256']:raise SystemExit('Archive identity mismatch: '+item['Package'])
 target.write_bytes(data)
 subprocess.run(['dpkg-deb','-x',str(target),str(root)],check=True)
print('Local extraction complete; not a complete container/package installation.')
