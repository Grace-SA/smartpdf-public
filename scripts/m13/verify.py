"""Independently inspect research PDFs with pypdf (not the Office engine)."""
import json, hashlib, gzip
from pathlib import Path
from pypdf import PdfReader

root=Path('.research/m13')
manifest=json.loads((root/'fixtures/manifest.json').read_text(encoding='utf8'))
checks=[]
for fixture in manifest:
    source=root/'fixtures'/(fixture['name']+'.docx')
    assert hashlib.sha256(source.read_bytes()).hexdigest()==fixture['sha256'], 'Source identity changed'
    path=root/'outputs'/('chromium-'+fixture['name']+'.pdf')
    r=PdfReader(path)
    text='\n'.join(page.extract_text() for page in r.pages)
    missing=[marker for marker in fixture['markers'] if marker not in text]
    duplicate=[marker for marker in fixture['markers'] if marker not in ['HEADER-M13','FOOTER-M13'] and text.count(marker)!=1]
    expected=fixture['expectedPages']
    geometry=[[float(p.mediabox.width),float(p.mediabox.height)] for p in r.pages]
    orientation=True
    if fixture['name']=='mixed-orientation':
        orientation=geometry[0][0]<geometry[0][1] and geometry[1][0]>geometry[1][1]
    pagination=len(r.pages)>1 if fixture['name'] in ['automatic-pagination','long-table'] else expected==len(r.pages)
    images=sum(len(p.images) for p in r.pages)
    image_ok=images>=1 if fixture['name']=='explicit-pages-table-image' else True
    row=dict(fixture=fixture['name'],inputSha256=fixture['sha256'],outputSha256=hashlib.sha256(path.read_bytes()).hexdigest(),
             pages=len(r.pages),missing=missing,duplicates=duplicate,geometry=geometry,images=images,
             structuralChecksPassed=not missing and not duplicate and orientation and pagination and image_ok)
    checks.append(row)
    assert row['structuralChecksPassed'],row
(root/'independent-checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'documents':len(checks),'pages':sum(x['pages'] for x in checks),'structuralChecks':'passed','visualReview':'separate; not implied by parser checks'}))
