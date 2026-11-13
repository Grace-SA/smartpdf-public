"""Offline, opt-in safety evaluation. Never downloads or publishes source data."""
import argparse
import hashlib
import json
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
import pypdfium2 as pdfium
from grid_probe import infer


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(path, expected):
    if digest(path) != expected:
        raise ValueError('Input hash mismatch: '+path.name)


def evaluate(corpus, references, output):
    output.mkdir(parents=True, exist_ok=False)
    manifest=json.loads((corpus/'manifest.json').read_text())
    results=[]
    for item in manifest:
        name=item['id']
        if Path(name).name != name or Path(item['file']).name != item['file']:
            raise ValueError('Unsafe manifest path')
        source=corpus/item['file']; reference=references/(name+'-str.xml')
        check(source,item['sha256']);check(reference,item['referenceSha256'])
        if reference.stat().st_size>5000000:raise ValueError('Reference too large')
        regions=ET.parse(reference).findall('.//region')
        # Predeclared selection: first annotated page per independent source.
        page_no=min(int(r.get('page')) for r in regions)
        expected=[r for r in regions if int(r.get('page'))==page_no]
        cells=[c for r in expected for c in r.findall('cell')]
        merged=sum(c.get('end-row',c.get('start-row'))!=c.get('start-row') or c.get('end-col',c.get('start-col'))!=c.get('start-col') for c in cells)
        expected_shape=None
        if len(expected)==1:
            expected_shape=[max(int(c.get('end-row',c.get('start-row'))) for c in cells)+1,max(int(c.get('end-col',c.get('start-col'))) for c in cells)+1]
        start=time.monotonic()
        with pdfium.PdfDocument(source) as document:
            page=document[page_no-1];w,h=page.get_size()
            scale=min(2.5,(16000000/(w*h))**.5)
            image=output/(name+'.png');page.render(scale=scale).to_pil().convert('RGB').save(image)
        ocr=output/name
        try:
            subprocess.run(['tesseract',str(image),str(ocr),'-l','eng','--psm','3','tsv'],capture_output=True,check=True,timeout=45)
            candidate=infer(image,ocr.with_suffix('.tsv'),output)
        except subprocess.TimeoutExpired:
            candidate={'status':'timeout'}
        except subprocess.CalledProcessError:
            candidate={'status':'ocr_error'}
        accepted=candidate['status']=='grid'
        shape=[len(candidate.get('ys',[]))-1,len(candidate.get('xs',[]))-1] if accepted else None
        shape_span_compatible=accepted and len(expected)==1 and merged==0 and shape==expected_shape
        exact=0
        if shape_span_compatible:
            for cell in cells:
                r,c=int(cell.get('start-row')),int(cell.get('start-col'))
                text=' '.join(''.join(cell.find('content').itertext()).split()) if cell.find('content') is not None else ''
                exact+=candidate['cell_crop_cells'][r][c]==text
        result={'id':name,'page':page_no,'source_sha256':item['sha256'],'reference_sha256':item['referenceSha256'],'expected_tables':len(expected),'expected_cells':len(cells),'expected_merged_cells':merged,'expected_shape':expected_shape,'status':candidate['status'],'predicted_shape':shape,'shape_span_compatible':bool(shape_span_compatible),'incompatible_grid_acceptance':bool(accepted and not shape_span_compatible),'exact_text_cells_when_shape_span_compatible':exact,'unassigned_word_count':len(candidate.get('unassigned',[])),'seconds':round(time.monotonic()-start,3)}
        results.append(result);print(json.dumps(result),flush=True)
    (output/'metrics.json').write_text(json.dumps(results,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus',type=Path,required=True)
    parser.add_argument('--references',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();evaluate(args.corpus,args.references,args.output)
