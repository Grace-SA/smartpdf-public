"""Build the Excel-only overlay after verifying the approved local baseline identity."""
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[2]
config = json.loads((root / 'config/excel-core.stirling-3.2.2.json').read_text())
baseline = subprocess.check_output(['docker', 'image', 'inspect', 'smartpdf-stirling-core:3.2.2-poc2', '--format', '{{.Id}}'], text=True).strip()
if baseline != config['baselineImageId']:
    raise SystemExit('Baseline image does not match the locked Excel baseline; no build performed.')
subprocess.run(['docker', 'build', '--pull=false', '--network=none', '-t', 'smartpdf-excel-core:3.2.2-rich', str(root / 'server/excel')], check=True)
result = subprocess.check_output(['docker', 'image', 'inspect', 'smartpdf-excel-core:3.2.2-rich', '--format', '{{.Id}}'], text=True).strip()
print(json.dumps({'imageId': result, 'baselineImageId': baseline, 'matchesAcceptancePin': result == config['imageId']}))
