"""Opt-in local public-source simulation and baseline/research cell comparison."""
import argparse,hashlib,json,os,subprocess,sys,tempfile
from pathlib import Path
import reportlab
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from concurrent.futures import ThreadPoolExecutor
import pypdfium2 as pdfium
import io
from openpyxl import load_workbook
R=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--source-directory',type=Path,required=True);p.add_argument('--repository',type=Path,required=True);p.add_argument('--output-directory',type=Path,required=True);p.add_argument('--enable-research',action='store_true');p.add_argument('--check-only',action='store_true');a=p.parse_args()
if not a.enable_research:p.error('Explicit research opt-in required')
if reportlab.Version!='4.4.9' or str(pdfium.PYPDFIUM_INFO)!='5.14.0' or str(pdfium.PDFIUM_INFO)!='156.0.8076.0':
 raise SystemExit('Renderer version mismatch; do not infer historical comparability')
for name,digest in json.loads((R/'baseline-sha256.json').read_text()).items():
 if hashlib.sha256((a.repository/'server/pdf-to-excel'/name).read_bytes()).hexdigest()!=digest:raise SystemExit('Baseline identity mismatch: '+name)
if a.check_only:
 print('Pinned renderer and baseline preflight passed');raise SystemExit(0)
a.output_directory.mkdir(parents=True,exist_ok=False)
results=[]
for item in json.loads((R/'public-sources.json').read_text()):
 source=a.source_directory/item['file']
 if hashlib.sha256(source.read_bytes()).hexdigest()!=item['sha256']:raise SystemExit('Public-source identity mismatch: '+item['id'])
 scan=a.output_directory/(item['id']+'-150dpi.pdf')
 document=canvas.Canvas(str(scan))
 with pdfium.PdfDocument(source) as native:
  for page in native:
   bitmap=page.render(scale=150/72,no_smoothtext=True,no_smoothpath=True,no_smoothimage=True)
   image=bitmap.to_pil().convert('RGB');width,height=page.get_size()
   document.setPageSize((width,height))
   document.drawImage(ImageReader(image),0,0,width=width,height=height)
   document.showPage();bitmap.close();page.close()
 document.save()
 def convert_case(pair):
  label,engine=pair
  target=a.output_directory/(item['id']+'-'+label+'.xlsx')
  subprocess.run([sys.executable,str(engine),str(scan),str(target),'{"ocr":true}'],check=True,timeout=180,stdout=subprocess.DEVNULL)
  return load_workbook(target)
 with ThreadPoolExecutor(max_workers=2) as pool:
  workbooks=list(pool.map(convert_case,[('baseline',a.repository/'server/pdf-to-excel/convert.py'),('research',R/'engine/convert.py')]))
 baseline,research=workbooks;assert baseline.sheetnames==research.sheetnames;changes=[]
 for x,y in zip(baseline,research):
  assert (x.max_row,x.max_column)==(y.max_row,y.max_column)
  assert set(map(str,x.merged_cells))==set(map(str,y.merged_cells))
  for row in x:
   for cell in row:
    if cell.value!=y[cell.coordinate].value:changes.append([x.title,cell.coordinate,cell.value,y[cell.coordinate].value])
 expected=[['Page 1 Table 1','A18',None,'3']] if item['id']=='rainfall_distribution' else []
 assert changes==expected,(item['id'],changes)
 results.append(dict(name=item['id'],nativeSha256=item['sha256'],simulationSha256=hashlib.sha256(scan.read_bytes()).hexdigest(),changes=changes))
(a.output_directory/'comparison.json').write_text(json.dumps(dict(renderer=str(pdfium.PYPDFIUM_INFO),pdfWrapper=reportlab.Version,results=results),indent=2))
print('Public reproduction passed: three source hashes, dimensions, merges and all cell differences checked.')
