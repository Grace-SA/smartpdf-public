"""Reproduce a bounded, native-only public PDF-to-PPT diagnostic.

Uses source-image baseline, not Stirling: results must not be called service
acceptance. Bag character recall is a diagnostic, not text correctness. Keep
raw PDFs and generated artifacts outside Git. Run in an isolated environment
with a process-level time budget, as for the conversion worker.
"""
import sys,json,subprocess,hashlib
from pathlib import Path
from contextlib import closing
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from pypdf import PdfReader,PdfWriter
import pypdfium2 as pdfium
from pptx import Presentation
from smartppt.pdf import inspect_pdf
from smartppt.preserve import convert_preserve
from smartppt.layout import native_slide
from smartppt.assisted import clear_shapes
from smartppt.render_gate import run_gate,render_presentations,metric
from smartppt.content_gate import enforce_content_safety
from smartppt.portable_fonts import try_portable_fonts
from smartppt.quality import normalized,numeric_tokens,shape_text
from smartppt.config import Settings
import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--inputs',type=Path,required=True,help='Local downloaded PDFs named dummy.pdf, fw9.pdf and attention.pdf')
parser.add_argument('--output',type=Path,required=True,help='New output directory; never use an existing directory')
parser.add_argument('--renderer',required=True)
args=parser.parse_args()
manifest=json.loads(Path(__file__).with_name('public-native-manifest.json').read_text())
# Verify the entire inventory before generating anything. No online downloads.
for item in manifest['documents']:
 source=args.inputs/(item['name']+'.pdf')
 if hashlib.sha256(source.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('public input hash mismatch: '+item['name'])
root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
settings=Settings(renderer_path=args.renderer)
results=[]
for item in manifest['documents']:
 name,selection=item['name'],item['pages']
 folder=root/name;folder.mkdir(exist_ok=True);source=folder/'source.pdf';reader=PdfReader(args.inputs/(name+'.pdf'));writer=PdfWriter()
 for n in selection:writer.add_page(reader.pages[n-1])
 writer.write(source)
 info=inspect_pdf(source);baseline=folder/'baseline.pptx';target=folder/'candidate.pptx';convert_preserve(source,baseline,info)
 prs=Presentation(baseline);report={'pages':[]}
 with pdfium.PdfDocument(source) as doc:
  for i in range(len(doc)):
   slide=prs.slides[i];clear_shapes(slide)
   with closing(doc[i]) as page:r=native_slide(prs,page,slide)
   report['pages'].append(dict(r,page=i+1))
 prs.save(target);print(name,'native',flush=True)
 report=run_gate(baseline,target,source,report,settings);print(name,'visual gated',flush=True)
 report=enforce_content_safety(source,target,info,report,settings);print(name,'content gated',flush=True)
 report=try_portable_fonts(source,target,report,settings);rendered=render_presentations([target],folder,settings)[0]
 rows=[];prs=Presentation(target)
 for i,s in enumerate(prs.slides):
  expected=subprocess.check_output(['pdftotext','-f',str(i+1),'-l',str(i+1),'-enc','UTF-8',str(source),'-'],timeout=60).decode()
  actual='\n'.join(shape_text(s.shapes));a=Counter(normalized(expected));b=Counter(normalized(actual));n=sum(a.values())
  rows.append({'source_page':selection[i],'reference_characters':n,'editable_characters':sum(b.values()),'bag_character_recall':sum((a&b).values())/n if n else None,'missing_numeric_tokens':dict(numeric_tokens(expected)-numeric_tokens(actual)),'extra_numeric_tokens':dict(numeric_tokens(actual)-numeric_tokens(expected)),'pixel':metric(source,rendered,i),'route':report['pages'][i]['route']})
 result={'sample':name,'source_sha256':item['sha256'],'source_pages':len(reader.pages),'selected_pages':selection,'results':rows,'report':report};results.append(result)
 (folder/'evidence.json').write_text(json.dumps(result,indent=2));print(json.dumps(rows),flush=True)
(root/'summary.json').write_text(json.dumps(results,indent=2))
