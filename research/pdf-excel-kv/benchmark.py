"""Isolated local comparator. Never commit PDF, XLSX or trace outputs."""
import argparse,atexit,hashlib,json,resource,sys,time
from pathlib import Path
from unittest.mock import patch
p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('output',type=Path);p.add_argument('--models',required=True,type=Path);p.add_argument('--enabled',action='store_true');p.add_argument('--pages');args=p.parse_args()
root=args.output;root.mkdir(parents=True,exist_ok=True);process_start=time.monotonic()
engine=Path(__file__).resolve().parents[2]/'server/pdf-to-excel';sys.path.insert(0,str(engine))
import os
os.environ['PDF_EXCEL_MODELS']=str(args.models.resolve())
import torch
from docling.datamodel.base_models import InputFormat
from adapter import build_converter
from instrumentation import install
from convert import convert
records=[];selection=build_converter(str(args.models.resolve()),enabled=args.enabled)
opts=selection.converter.format_to_options[InputFormat.PDF].pipeline_options
assert opts.document_timeout==150 and opts.accelerator_options.num_threads==2
(root/'code.json').write_text(json.dumps({f.name:hashlib.sha256(f.read_bytes()).hexdigest()for f in Path(__file__).parent.iterdir()if f.is_file()and f.suffix in('.py','.json')},indent=2))
def plain(x):
 if isinstance(x,torch.Tensor):return x.detach().cpu().tolist()
 if isinstance(x,(list,tuple)):return[plain(v)for v in x]
 if isinstance(x,dict):return{k:plain(v)for k,v in x.items()}
 return x
started=time.monotonic();selection.converter.initialize_pipeline(InputFormat.PDF)
pipelines=list(selection.converter.initialized_pipelines.values());assert len(pipelines)==1
predictor=pipelines[0].table_model.tf_predictor;previous=predictor.predict;had='predict'in predictor.__dict__;instance=predictor.__dict__.get('predict')
def observed(*a,**kw):
 logits=[];prediction=[]
 try:
  with install(predictor._model,'reference',lambda x:logits.append(plain(x)),lambda x:prediction.append(plain(x))):return previous(*a,**kw)
 finally:records.append(dict(logits=logits,prediction=prediction))
predictor.predict=observed
original_convert=selection.converter.convert
def capture(*a,**kw):
 r=original_convert(*a,**kw);(root/'raw.json').write_text(json.dumps(dict(status=str(r.status),tables=[t.model_dump(mode='json')for t in r.document.tables])));return r
selection.converter.convert=capture
options={'ocr':False}
if args.pages:options['pages']=args.pages
try:
 with patch('layout_tables.converter_for',return_value=selection.converter):result=convert(str(args.input),str(root/'output.xlsx'),options)
 status='converted'
except Exception as e:result=dict(error=type(e).__name__,message=str(e));status='refused'
finally:
 if had:predictor.predict=instance
 else:delattr(predictor,'predict')
 selection.converter.convert=original_convert
report=dict(requested=args.enabled,active=selection.active,reason=selection.reason,status=status,seconds=time.monotonic()-started,threads=torch.get_num_threads(),deadline=opts.document_timeout,maxrssKiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,inputSha256=hashlib.sha256(args.input.read_bytes()).hexdigest(),result=result)
(root/'result.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items()if k!='result'}),flush=True)
def finished():
 (root/'traces.json').write_text(json.dumps(records))
 (root/'exit.json').write_text(json.dumps(dict(processSeconds=time.monotonic()-process_start,states=selection.states,maxrssKiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),indent=2))
atexit.register(finished)
