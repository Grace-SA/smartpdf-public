"""Run reviewed synthetic XLSX through a fixed, isolated Stirling core candidate."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'server/excel'))
from preflight import prepare, Rejected

IMAGE = json.loads((ROOT / 'config/excel-core.stirling-3.2.2.json').read_text())['imageId']

def main(root, only=None):
    root = Path(root)
    name = 'smartpdf-excel-poc-' + uuid.uuid4().hex
    def docker(*args):
        return subprocess.run(['docker', *args], check=True, capture_output=True, timeout=60).stdout
    network = 'smartpdf-word'
    if not json.loads(docker('network', 'inspect', network))[0]['Internal']:
        raise RuntimeError('Internal network required')
    result = json.loads((root / 'engine-results.json').read_text()) if only is not None and (root / 'engine-results.json').exists() else []
    try:
        docker('create', '--name', name, '--network', network, '--memory', '2560m', '--memory-swap', '2560m', '--cpus', '2', '--pids-limit', '512', '--security-opt', 'no-new-privileges', '--cap-drop', 'NET_RAW', '-e', 'SECURITY_ENABLELOGIN=false', '-e', 'JAVA_CUSTOM_OPTS=-Xms256m -Xmx1280m -XX:TieredStopAtLevel=1 -XX:ActiveProcessorCount=2', '-e', 'SPRING_MAIN_LAZY_INITIALIZATION=true', IMAGE)
        docker('start', name)
        info = json.loads(docker('inspect', name))[0]
        base = 'http://' + info['NetworkSettings']['Networks'][network]['IPAddress'] + ':8080'
        for _ in range(150):
            try:
                with urllib.request.urlopen(base + '/api/v1/info/status', timeout=2) as response:
                    if response.status == 200:
                        break
            except Exception:
                time.sleep(1)
        cases = json.loads((root / 'cases.json').read_text()) if (root / 'cases.json').exists() else [dict(input=stem, sheets=sheets, scale=scale) for stem, sheets, scale in [('selection', [0], 'keep'), ('selection', [1], 'keep'), ('selection', [0, 1], 'keep'), ('wide-long', [0], 'keep'), ('wide-long', [0], 'width'), ('wide-long', [0], 'page'), ('print-area', [0], 'width'), ('formulas', [0], 'keep')]]
        for index, case in enumerate(cases):
            if only is not None and index != only: continue
            result = [item for item in result if item['case'] != index]
            stem, sheets, scale = case['input'], case['sheets'], case['scale']
            source = root / (stem + '.xlsx')
            prepared = root / f'prepared-{index}.xlsx'
            try:
                warnings = prepare(source, prepared, {k: v for k, v in case.items() if k in {'sheets', 'scale', 'orientation', 'paper'}})
            except Rejected:
                if not case.get('expectedReject'): raise
                result.append({'case': index, 'refused': True})
                print(json.dumps(result[-1]), flush=True)
                continue
            if case.get('expectedReject'): raise RuntimeError('Expected refusal did not happen')
            boundary = uuid.uuid4().hex
            body = (f'--{boundary}\r\nContent-Disposition: form-data; name="fileInput"; filename="document.xlsx"\r\nContent-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n').encode() + prepared.read_bytes() + (f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="useStirlingOfficeConvert"\r\n\r\nfalse\r\n--{boundary}--\r\n').encode()
            request = urllib.request.Request(base + '/api/v1/convert/file/pdf', body, {'Content-Type': 'multipart/form-data; boundary=' + boundary}, method='POST')
            start = time.monotonic()
            with urllib.request.urlopen(request, timeout=90) as response:
                data = response.read(30 * 1024**2 + 1)
            if not data.startswith(b'%PDF-') or len(data) > 30 * 1024**2:
                raise RuntimeError('Invalid PDF')
            target = root / f'output-{index}.pdf'
            target.write_bytes(data)
            result.append({'case': index, 'input': stem, 'sheets': sheets, 'scale': scale, 'sha256': hashlib.sha256(data).hexdigest(), 'seconds': round(time.monotonic()-start, 2), 'warnings': warnings})
            print(json.dumps(result[-1]), flush=True)
        (root / 'engine-results.json').write_text(json.dumps(sorted(result, key=lambda item: item['case']), indent=2))
    finally:
        docker('rm', '-f', name)

if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else None)
