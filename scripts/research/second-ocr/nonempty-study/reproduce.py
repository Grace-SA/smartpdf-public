"""Opt-in, fixed-public-input OCR diagnostic; never changes a conversion value."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import resource
import sys
import time

HERE = Path(__file__).resolve().parent

def check_source(path, spec):
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('Unexpected source size')
    if hashlib.sha256(path.read_bytes()).hexdigest() != spec['sourceSha256']:
        raise ValueError('Source hash mismatch; refuse before parsing')

def check_runtime(spec):
    for name, expected in spec['versions'].items():
        if importlib.metadata.version(name) != expected:
            raise ValueError('Runtime version mismatch: ' + name)
    import rapidocr_onnxruntime
    root = Path(rapidocr_onnxruntime.__file__).parent
    for relative, expected in spec['primaryModels'].items():
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != expected:
            raise ValueError('Primary model hash mismatch')

def make_cases(page, fields):
    import cv2
    import numpy as np
    cases = []
    for field in fields:
        name = field['name']; x0, y0, x1, y1 = field['box']
        if not (8 <= x0 < x1 <= page.shape[1]-8 and 8 <= y0 < y1 <= page.shape[0]-8):
            raise ValueError('Crop outside fixed page')
        base = page[y0:y1, x0:x1].copy()
        for pad in (0, 4, 8):
            cases.append((name+'-pad'+str(pad), page[y0-pad:y1+pad,x0-pad:x1+pad].copy(), field['manualSource']))
        cases.append((name+'-rot180', cv2.rotate(base,cv2.ROTATE_180), None))
        if name == 'Delaware':
            covered = base.copy(); covered[base.shape[0]//2:,:base.shape[1]//2] = 255
            cases.append((name+'-lower-left-covered', covered, None))
            cases.append((name+'-duplicate-adjacent', np.concatenate([base,np.full((base.shape[0],4,3),255,np.uint8),base],axis=1), None))
        else:
            cases.append((name+'-left-edge-clipped', base[:,4:].copy(), None))
            cases.append((name+'-fully-covered', np.full_like(base,255), None))
    if len(cases) != 12 or any(c.shape[0]*c.shape[1]>16384 for _,c,_ in cases):
        raise ValueError('Diagnostic exceeds fixed second-reader budget')
    return cases

def run(source, output):
    import numpy as np
    spec = json.loads((HERE/'inputs.json').read_text())
    check_source(source, spec); check_runtime(spec)
    from docling_parse.pdf_parser import DoclingThreadedPdfParser,ThreadedPdfParserConfig,RenderConfig
    parser = DoclingThreadedPdfParser(ThreadedPdfParserConfig(threads=1,render_config=RenderConfig()))
    parser.load(source,page_numbers=[spec['page']])
    page = None
    for result in parser.iterate_results():
        if page is not None: raise ValueError('Unexpected additional page')
        page = np.asarray(result.get_image(scale=spec['renderScale']).convert('RGB'))
    if page is None or list(page.shape[:2][::-1]) != spec['rasterSize'] or hashlib.sha256(page.tobytes()).hexdigest()!=spec['rasterRgbSha256']:
        raise ValueError('Final rendered pixels differ from fixed source evidence')
    from rapidocr_onnxruntime import RapidOCR
    sys.path.insert(0,str(HERE.parent/'engine'))
    from second_ocr import research_job
    reader = RapidOCR(intra_op_num_threads=2,inter_op_num_threads=2)
    rows = []
    with research_job() as job:
        for name,crop,expected in make_cases(page,spec['fields']):
            start=time.monotonic();direct,_=reader.text_rec([crop.copy()]);direct_s=time.monotonic()-start
            start=time.monotonic();oriented,angles,_=reader.text_cls([crop.copy()]);classified,_=reader.text_rec(oriented);angle_s=time.monotonic()-start
            start=time.monotonic();second=job.recognize(crop);second_s=time.monotonic()-start
            rows.append(dict(name=name,shape=list(crop.shape),sha256=hashlib.sha256(crop.tobytes()).hexdigest(),expectedUnchangedSource=expected,primaryDirect=direct,primaryWithAngle=classified,angle=angles,second=second,primarySeconds=direct_s,angleAndRecognitionSeconds=angle_s,secondWallSeconds=second_s))
        report={'sourceSha256':spec['sourceSha256'],'rasterRgbSha256':spec['rasterRgbSha256'],'cases':rows,'jobBudget':job.budget,'jobMeasurements':job.measurements,'childPeakRssKiB':resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,'decision':'No automatic replacement approved; require manual source review.','limits':'12-call fixed diagnostic, not general accuracy, full conversion overhead or deployment acceptance.'}
    output.write_text(json.dumps(report,indent=2,default=lambda x:x.tolist() if hasattr(x,'tolist') else float(x))+'\n')

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enable-research',action='store_true');p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if not a.enable_research:p.error('Explicit --enable-research is required')
    run(a.source,a.output)
