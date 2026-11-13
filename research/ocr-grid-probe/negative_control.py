"""Opt-in negative control: manually reviewed scan with no table."""
import argparse,json,subprocess
from pathlib import Path
import pypdfium2 as pdfium
from evaluate import check
from grid_probe import infer

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pdf',type=Path,required=True)
    p.add_argument('--sha256',required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();check(a.pdf,a.sha256);a.output.mkdir(parents=True,exist_ok=False)
    with pdfium.PdfDocument(a.pdf) as doc:
        page=doc[0];w,h=page.get_size();scale=min(2.5,(16000000/(w*h))**.5)
        image=a.output/'page.png';page.render(scale=scale).to_pil().convert('RGB').save(image)
    subprocess.run(['tesseract',str(image),str(a.output/'page'),'-l','eng','--psm','3','tsv'],capture_output=True,check=True,timeout=45)
    r=infer(image,a.output/'page.tsv',a.output)
    metrics={'source_sha256':a.sha256,'page':1,'label_method':'manual visual review: no table','expected_tables':0,'status':r['status'],'false_positive_table':r['status']=='grid'}
    (a.output/'metrics.json').write_text(json.dumps(metrics,indent=2)+'\n');print(json.dumps(metrics))
if __name__=='__main__':main()
