"""Independent PDF text + raster checks for frozen rich-content cases."""
import hashlib
import json
from pathlib import Path
import re
import sys
import pymupdf
from PIL import Image, ImageDraw

root = Path(sys.argv[1])
cases = json.loads((root / 'cases.json').read_text())
tiles = []; results = []
for index, case in enumerate(cases):
    assert hashlib.sha256((root / (case['input'] + '.xlsx')).read_bytes()).hexdigest() == case['sourceSha256']
    with pymupdf.open(root / f'output-{index}.pdf') as doc:
        text = '\n'.join(page.get_text() for page in doc)
        normal = re.sub(r'\s+', '', text)
        missing = [value for value in case['expected'] if re.sub(r'\s+', '', value) not in normal]
        leaked = [value for value in case['forbidden'] if value in text]
        pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(1, 1), alpha=False)
        image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
        coloured = sum(max(p) - min(p) > 60 and min(p) < 220 for p in image.getdata())
        # All cases contain actual chart/image/conditional-format/table colour,
        # except the plain filtered range, whose criterion is row inclusion.
        visual = coloured >= 200 or case['visual'] == 'filter'
        passed = not missing and not leaked and visual and len(doc) == 1
        results.append(dict(case=index, feature=case['input'], pages=len(doc), missing=missing, leaked=leaked,
                            colouredPixels=coloured, passed=passed))
        image.thumbnail((580, 370))
        tile = Image.new('RGB', (600, 405), '#e2e8f0')
        ImageDraw.Draw(tile).text((10, 8), f'{index}: {case["input"]}; coloured={coloured}; passed={passed}', fill='black')
        tile.paste(image, (10, 30)); tiles.append(tile)
collage = Image.new('RGB', (600 * 4, 405 * ((len(tiles) + 3) // 4)), 'white')
for index, tile in enumerate(tiles): collage.paste(tile, ((index % 4) * 600, (index // 4) * 405))
collage.save(root / 'rich-review.png')
(root / 'independent.json').write_text(json.dumps(results, indent=2))
print(json.dumps({'cases':len(results), 'passed':sum(r['passed'] for r in results), 'failures':[r for r in results if not r['passed']]}, indent=2))
assert all(r['passed'] for r in results)
