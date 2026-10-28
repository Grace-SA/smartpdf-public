"""Independent PDF checks; conversion successes are not accepted without these."""
import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from pypdf import PdfReader
import pdfplumber

def normalize(text):
    return re.sub(r'\s+','',unicodedata.normalize('NFC',text))

def inspect(path,expected):
    reader=PdfReader(path)
    pages=[p.extract_text() or '' for p in reader.pages]
    normalized=[normalize(t) for t in pages]
    text=''.join(normalized)
    repeated={'HEADER-M13','FOOTER-M13',expected.get('repeatedHeader'),expected.get('repeatedFooter')}
    missing=[m for m in expected['markers'] if normalize(m) not in text]
    duplicates=[m for m in expected['markers'] if m not in repeated and text.count(normalize(m))!=1]
    geometry=[[float(p.mediabox.width),float(p.mediabox.height)] for p in reader.pages]
    faults=[]
    if expected.get('expectedPages') is not None and len(pages)!=expected['expectedPages']:
        faults.append('explicit_page_count')
    if expected.get('minPages') is not None and len(pages)<expected['minPages']:
        faults.append('automatic_pagination')
    if expected['name'] in ['automatic-pagination','long-table'] and len(pages)<2:
        faults.append('original_automatic_pagination')
    orientations=expected.get('orientations')
    if expected['name']=='mixed-orientation':orientations=['portrait','landscape']
    if orientations:
        observed=['landscape' if w>h else 'portrait' for w,h in geometry]
        if observed!=orientations:faults.append('orientation')
    for page,markers in expected.get('pageMarkers',{}).items():
        if int(page)>len(pages) or any(normalize(m) not in normalized[int(page)-1] for m in markers):
            faults.append('page_marker_assignment')
    for key in ['repeatedHeader','repeatedFooter']:
        if expected.get(key) and any(normalize(expected[key]) not in t for t in normalized):
            faults.append(key)
    fontnames=set();bounds=[];glyphs=[]
    with pdfplumber.open(path) as document:
        for number,page in enumerate(document.pages,1):
            for char in page.chars:
                fontnames.add(char.get('fontname',''))
                glyphs.append([number,char['text'],round(char['x0'],2),round(char['top'],2),
                               round(char['x1'],2),round(char['bottom'],2),char.get('fontname','')])
                if char['text'].strip() and (char['x0'] < -1 or char['x1']>page.width+1 or
                    char['top'] < -1 or char['bottom']>page.height+1):
                    bounds.append({'page':number,'text':char['text'],'box':[char['x0'],char['top'],char['x1'],char['bottom']]})
    if bounds:faults.append('glyph_outside_page')
    if missing:faults.append('missing_text')
    if duplicates:faults.append('duplicate_body_marker')
    return {'name':expected['name'],'pages':len(pages),'geometry':geometry,'missing':missing,'duplicates':duplicates,
            'fonts':sorted(fontnames),'outOfPage':bounds[:30],'faults':faults,
            'structuralPass':not faults,'pageTextSha256':[hashlib.sha256(t.encode()).hexdigest() for t in normalized],
            'glyphLayoutSha256':hashlib.sha256(json.dumps(glyphs,ensure_ascii=False).encode()).hexdigest(),
            'visualReview':'pending: independently render and inspect every page'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--variant',choices=['default-fonts','noto-fonts'],required=True);args=p.parse_args()
    root=Path('.research/m13/gotenberg')/args.variant
    results=json.loads((root/'results.json').read_text(encoding='utf8'))
    manifests={}
    for directory,cohort in [(Path('.research/m13/fixtures'),'original'),(Path('.research/m13/gotenberg/fixtures'),'extended')]:
        for item in json.loads((directory/'manifest.json').read_text(encoding='utf8')):
            assert hashlib.sha256((directory/(item['name']+'.docx')).read_bytes()).hexdigest()==item['sha256']
            manifests[cohort,item['name']]=item
    checks=[];repeated={}
    for row in results['runs']:
        if 'error' in row or 'file' not in row:
            checks.append({'name':row['name'],'cycle':row['cycle'],'structuralPass':False,'faults':['conversion_failed']});continue
        path=root/row['file']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==row['outputSha256']
        check=inspect(path,manifests[row['cohort'],row['name']]);check.update(cycle=row['cycle'],file=row['file'])
        key=(row['cohort'],row['name']);signature=(check['geometry'],check['pageTextSha256'],check['glyphLayoutSha256'])
        if key in repeated and repeated[key]!=signature:
            check['faults'].append('repeat_layout_or_text_changed');check['structuralPass']=False
        repeated[key]=signature;checks.append(check)
    output={'variant':args.variant,'checks':checks,'negativeRuns':results['negativeRuns'],
            'visualInspectionCompleted':False,'wordReferenceComparisonCompleted':False}
    (root/'independent-checks.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'outputs':len(checks),'structuralPassed':sum(c['structuralPass'] for c in checks),'visualReview':'not implied'}))
    raise SystemExit(0 if all(c['structuralPass'] for c in checks) and
                     all(c['expectedRejection'] for c in results['negativeRuns']) else 1)

if __name__=='__main__':main()
