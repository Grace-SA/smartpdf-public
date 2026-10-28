"""Read-only comparison of frozen synthetic Word references and native PoC PDFs.

Run from the repository root. Raw PDFs, extracted content and page images stay
under ignored .research; this script never uploads evidence or changes sources.
"""
import hashlib
import json
import re
import subprocess
from pathlib import Path

import pdfplumber
from PIL import Image, ImageDraw
from pypdf import PdfReader

ROOT = Path('.research/m13')
OUT = ROOT / 'word-reference'


def inspect(path, markers):
    reader = PdfReader(path)
    pages = []
    with pdfplumber.open(path) as pdf:
        for index, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ''
            found = {}
            for marker in markers:
                # Word can insert inferred spaces between glyph groups, e.g.
                # LONGROW -001. Match optional whitespace but retain raw text.
                pattern = r'\s*'.join(re.escape(c) for c in marker)
                hits = page.search(pattern, regex=True)
                if hits:
                    found[marker] = [
                        [round(h[k], 3) for k in ['x0', 'top', 'x1', 'bottom']]
                        for h in hits
                    ]
            pages.append(dict(page=index, width=round(page.width, 3),
                              height=round(page.height, 3), markers=found,
                              fonts=sorted({c['fontname'] for c in page.chars}),
                              images=len(page.images), lines=len(page.lines),
                              rects=len(page.rects), text=text))
    return dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                bytes=path.stat().st_size,
                creator=str(reader.metadata.get('/Creator', '')),
                producer=str(reader.metadata.get('/Producer', '')), pages=pages)


def main():
    records = []
    contact = []
    renderdir = OUT / 'rendered'
    renderdir.mkdir(exist_ok=True)
    for directory, kind in [(ROOT / 'fixtures', 'original'),
                            (ROOT / 'gotenberg/fixtures', 'extended')]:
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf8'))
        for item in manifest:
            name = item['name']
            reference = OUT / 'word-pdf' / (name + '.pdf')
            if not reference.exists():
                records.append(dict(name=name, referenceMissing=True))
                continue
            markers = [m for m in item['markers'] if m.isascii()]
            for key in ['repeatedHeader', 'repeatedFooter']:
                if item.get(key) and item[key] not in markers:
                    markers.append(item[key])
            word = inspect(reference, markers)
            assert 'Word' in word['producer'], 'Expected actual Microsoft Word export'
            row = dict(name=name, inputSha256=item['sha256'], word=word, variants={})
            assert hashlib.sha256((directory/(name+'.docx')).read_bytes()).hexdigest() == item['sha256'], 'Frozen source changed'
            prefix = renderdir / name
            subprocess.run(['pdftoppm', '-r', '100', '-png', str(reference), str(prefix)],
                           check=True, capture_output=True)
            for variant in ['default-fonts', 'noto-fonts']:
                native = ROOT / 'gotenberg' / variant / f'1-{kind}-{name}.pdf'
                engine = inspect(native, markers)
                comparison = []
                for page_index in range(max(len(word['pages']), len(engine['pages']))):
                    wp = word['pages'][page_index] if page_index < len(word['pages']) else None
                    lp = engine['pages'][page_index] if page_index < len(engine['pages']) else None
                    shared = sorted(set(wp['markers'] if wp else {}) & set(lp['markers'] if lp else {}))
                    deltas = [max(abs(a-b) for a,b in zip(wp['markers'][m][0],lp['markers'][m][0]))
                              for m in shared]
                    comparison.append(dict(page=page_index+1, wordPresent=wp is not None,
                        nativePresent=lp is not None, sharedMarkers=len(shared),
                        wordOnlyMarkers=sorted(set(wp['markers'] if wp else {})-set(shared)),
                        nativeOnlyMarkers=sorted(set(lp['markers'] if lp else {})-set(shared)),
                        maxMarkerBoxDeltaPt=round(max(deltas),3) if deltas else None))
                row['variants'][variant] = dict(pdf=engine, pageComparison=comparison)
                row['variants'][variant]['missingMarkers'] = sorted(set(markers)-
                    {m for p in engine['pages'] for m in p['markers']})
                row['variants'][variant]['repeatedMarkerFailures'] = [
                    dict(page=p['page'], marker=item[key])
                    for p in engine['pages'] for key in ['repeatedHeader','repeatedFooter']
                    if item.get(key) and item[key] not in p['markers']]
            row['wordMissingMarkers'] = sorted(set(markers)-
                {m for p in word['pages'] for m in p['markers']})
            records.append(row)
            for page_index in range(max(len(word['pages']),len(row['variants']['noto-fonts']['pdf']['pages']))):
                contact.append((name,page_index+1,renderdir/f'{name}-{page_index+1}.png',
                    ROOT/'gotenberg/noto-fonts/rendered'/f'1-{kind}-{name}-{page_index+1}.png'))
    (OUT/'comparison.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf8')
    for start in range(0,len(contact),6):
        sheet=Image.new('RGB',(1500,2190),'#ccd2da');draw=ImageDraw.Draw(sheet)
        for offset,(name,page,wordpath,nativepath) in enumerate(contact[start:start+6]):
            x=(offset%2)*750;y=(offset//2)*730
            draw.text((x+8,y+5),f'{name} / page {page} : WORD | NOTO',fill='black')
            for side,path in enumerate([wordpath,nativepath]):
                if path.exists():
                    im=Image.open(path).convert('RGB');im.thumbnail((363,690))
                    sheet.paste(im,(x+side*375+(375-im.width)//2,y+28))
                else:draw.text((x+side*375+20,y+80),'NO PAGE',fill='red')
        sheet.save(renderdir/f'comparison-{start//6+1}.png')
    summary=[]
    for row in records:
        if row.get('referenceMissing'):
            summary.append(row);continue
        result=dict(name=row['name'],wordPages=len(row['word']['pages']))
        for variant,data in row['variants'].items():
            result[variant]=dict(pages=len(data['pdf']['pages']),
                missingMarkers=data['missingMarkers'],
                repeatedMarkerFailures=data['repeatedMarkerFailures'],
                markerPageDifferences=sum(bool(p['wordOnlyMarkers'] or p['nativeOnlyMarkers']) for p in data['pageComparison']),
                maxMarkerBoxDeltaPt=max([p['maxMarkerBoxDeltaPt'] or 0 for p in data['pageComparison']]))
        result['wordMissingMarkers']=row['wordMissingMarkers']
        summary.append(result)
    (OUT/'comparison-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    main()
