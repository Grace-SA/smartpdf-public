"""Independently inspect complete typical PDFs; no one-page/text-only shortcut."""
import hashlib
import json
from pathlib import Path
import re
import statistics
import sys
import pymupdf
from PIL import Image, ImageDraw

root = Path(sys.argv[1]); cases = json.loads((root / 'cases.json').read_text(encoding='utf-8')); results = []; tiles = []
for index, case in enumerate(cases):
    assert hashlib.sha256((root / (case['input'] + '.xlsx')).read_bytes()).hexdigest() == case['sourceSha256']
    with pymupdf.open(root / f'output-{index}.pdf') as doc:
        texts = []; sizes = []; outside = 0
        for page in doc:
            texts.append(page.get_text())
            for block in page.get_text('dict')['blocks']:
                for line in block.get('lines', []):
                    for span in line['spans']:
                        if not span['text'].strip(): continue
                        sizes.append(span['size']); box = pymupdf.Rect(span['bbox'])
                        outside += int(box.x0 < -2 or box.y0 < -2 or box.x1 > page.rect.width + 2 or box.y1 > page.rect.height + 2)
        text = re.sub(r'\s+', '', '\n'.join(texts))
        markers = set(re.findall(r'(?:S[23]-)?T[0-9]{5}-[0-9]{2}', text))
        def present(value):
            value = re.sub(r'\s+', '', value)
            return value in markers if re.fullmatch(r'(?:S[23]-)?T[0-9]{5}-[0-9]{2}', value) else value in text
        missing = [s for s in case['expected'] if not present(s)]
        leaked = [s for s in case['forbidden'] if present(s)]
        header = not case['repeatHeader'] or all('COL-' in t for t in texts)
        key_column = not case.get('repeatKeyColumn') or all(any(w[4] == 'COL-01' for w in p.get_text('words')) for p in doc)
        words = doc[0].get_text('words')
        heading_y = next((w[1] for w in words if w[4] == 'COL-01'), -100)
        headings = {w[4] for w in words if abs(w[1] - heading_y) <= 4}
        last_heading = '32' if case['input'] == 'attendance' else f'COL-{case.get("singlePanelColumns") or 0:02}'
        single_panel = not case.get('singlePanelColumns') or last_heading in headings
        median = statistics.median(sizes) if sizes else 0
        tiny = sum(s < 7 for s in sizes) / max(1, len(sizes))
        passed = not missing and not leaked and header and key_column and single_panel and median >= case['minMedianFont'] - .1 and tiny < .01 and outside == 0 and 0 < len(doc) <= case['maxPages']
        results.append(dict(case=index, type=case['input'], pages=len(doc), missing=missing[:10], leaked=leaked[:10], medianFont=round(median, 2), smallFontFraction=round(tiny, 4), outsideText=outside, repeatedHeader=header, repeatedKeyColumn=key_column, singlePanel=single_panel, passed=passed))
        for label, number in [('first', 0), ('last', len(doc)-1)]:
            pix = doc[number].get_pixmap(matrix=pymupdf.Matrix(.85, .85), alpha=False); im = Image.frombytes('RGB', (pix.width, pix.height), pix.samples); im.thumbnail((560, 390))
            tile = Image.new('RGB', (580, 430), '#e8edf4'); ImageDraw.Draw(tile).text((10, 8), f'{case["input"]} / {label} / {len(doc)} pages / {median:.1f}pt / {passed}', fill='black'); tile.paste(im, (10, 32)); tiles.append(tile)
overview = Image.new('RGB', (580 * 4, 430 * ((len(tiles)+3)//4)), 'white')
for i, tile in enumerate(tiles): overview.paste(tile, ((i%4)*580, (i//4)*430))
overview.save(root / 'layout-review.png'); (root / 'independent.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
print(json.dumps({'cases':len(results), 'passed':sum(r['passed'] for r in results), 'results':results}, indent=2)); assert all(r['passed'] for r in results)
