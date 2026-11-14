"""Explicit local research setup; never installs packages or changes production."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--repository',type=Path,required=True);p.add_argument('--extracted-debian-root',type=Path,required=True);a=p.parse_args()
base=a.repository.resolve()/'server/pdf-to-excel'
expected=json.loads((R/'baseline-sha256.json').read_text())
for name,digest in expected.items():
 if hashlib.sha256((base/name).read_bytes()).hexdigest()!=digest:raise SystemExit('Pinned baseline mismatch: '+name)
for name in expected:shutil.copyfile(base/name,R/'engine'/name)
subprocess.run(['patch','--batch','--fuzz=0',str(R/'engine/convert.py'),str(R/'converter.patch')],check=True)
c=json.loads((R/'engine-lock.template.json').read_text())
for key in ('binary','model','library','libdir','data'):c[key]=str(a.extracted_debian_root.resolve()/c[key])
for key,digest in c['sha256'].items():
 if hashlib.sha256(Path(c[key]).read_bytes()).hexdigest()!=digest:raise SystemExit('Pinned engine mismatch: '+key)
(R/'engine-lock.json').write_text(json.dumps(c,indent=2))
print('Prepared isolated research only. Production files untouched.')
