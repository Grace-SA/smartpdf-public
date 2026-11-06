"""Exercise the production per-document runner with frozen synthetic case identities."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

repo = Path(__file__).resolve().parents[2]
root = Path(sys.argv[1]).resolve()
results = []
for index, case in enumerate(json.loads((root / 'cases.json').read_text())):
    source = root / (case['input'] + '.xlsx')
    if hashlib.sha256(source.read_bytes()).hexdigest() != case['sourceSha256']:
        raise RuntimeError('Frozen source identity changed')
    job = root / f'job-{index}'
    job.mkdir(exist_ok=True)
    shutil.copyfile(source, job / 'input.xlsx')
    (job / 'options.json').write_text(json.dumps({k: v for k, v in case.items() if k in {'sheets', 'scale', 'orientation', 'paper'}}))
    started = time.monotonic()
    process = subprocess.run([sys.executable, '-B', str(repo / 'server/word/runner.py'), str(job), 'excel'], capture_output=True, text=True, timeout=300)
    (job / 'runner.log').write_text(process.stdout + process.stderr)
    refused = 'INPUT_REJECTED' in process.stdout
    if case.get('expectedReject'):
        if not refused: raise RuntimeError('Expected refusal did not happen')
    else:
        if process.returncode or not (job / 'output.pdf').is_file(): raise RuntimeError(f'Case {index} failed; see local runner log')
        shutil.copyfile(job / 'output.pdf', root / f'output-{index}.pdf')
    results.append({'case': index, 'refused': refused, 'seconds': round(time.monotonic() - started, 3)})
    (root / 'engine-results.json').write_text(json.dumps(results, indent=2))
    print(json.dumps(results[-1]), flush=True)
