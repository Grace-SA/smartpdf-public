"""Fixed-coordinate multi-resolution ink diagnostic, never an acceptance verdict.

Integer-point ROIs (union font boxes rounded outward plus 1pt) are frozen once.
This differs from public-native-ink.py's padding; its existing 216dpi results
remain untouched. Source-image baseline error is reported, never subtracted.
"""
import argparse,hashlib,importlib.util,json,math,os,stat,statistics,subprocess,tempfile,time
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
DPIS=(144,216,288,432)
MAX_SECONDS=600


class Deadline:
 def __init__(self,seconds=MAX_SECONDS):
  if not math.isfinite(seconds) or not 0<seconds<=MAX_SECONDS:raise ValueError('invalid diagnostic time budget')
  self.end=time.monotonic()+seconds
 def remaining(self):
  left=self.end-time.monotonic()
  if left<=0:raise TimeoutError('multi-resolution diagnostic wall budget exceeded')
  return left
 def run(self,command,**kwargs):
  kwargs['timeout']=min(kwargs.get('timeout',60),60,self.remaining())
  if kwargs.get('stderr')==subprocess.PIPE:
   # Poppler can emit many errors for malformed PDFs. Capture them on disk,
   # not an unbounded memory pipe; the same child cap bounds its PNG output.
   import resource
   def render_limit():resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024*1024,64*1024*1024))
   kwargs.setdefault('preexec_fn',render_limit)
   with tempfile.TemporaryFile() as errors:
    kwargs['stderr']=errors
    result=subprocess.run(command,**kwargs)
  else:result=subprocess.run(command,**kwargs)
  self.remaining();return result


def load_ink(dpi,deadline=None):
 if dpi not in DPIS:raise ValueError('unsupported diagnostic DPI')
 path=Path(__file__).with_name('public-native-ink.py')
 spec=importlib.util.spec_from_file_location('independent_ink_'+str(dpi),path)
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 module.DPI=dpi;module.SCALE=dpi/72
 if deadline is not None:module.subprocess=SimpleNamespace(run=deadline.run,DEVNULL=subprocess.DEVNULL,PIPE=subprocess.PIPE)
 return module


def copy_and_digest(path,target,limit,deadline):
 deadline.remaining()
 # Opening nonblocking then checking the descriptor also rejects a path raced
 # from a regular file to a FIFO between validation and open.
 fd=os.open(path,os.O_RDONLY|getattr(os,'O_NONBLOCK',0))
 try:
  info=os.fstat(fd)
  if not stat.S_ISREG(info.st_mode):raise ValueError('input must be a regular file')
  if info.st_size>limit:raise ValueError('input file resource bound exceeded')
  stream=os.fdopen(fd,'rb')
 except BaseException:
  os.close(fd);raise
 with stream:
  result=hashlib.sha256();size=0
  with target.open('xb') if target is not None else nullcontext(None) as output:
   while chunk:=stream.read(1024*1024):
    deadline.remaining();size+=len(chunk)
    if size>limit:raise ValueError('input file resource bound exceeded')
    result.update(chunk)
    if output is not None:output.write(chunk)
 return result.hexdigest()


def digest(path,limit,deadline):
 return copy_and_digest(path,None,limit,deadline)


def fixed_rows(ink,dimensions,source,rendered):
 rows=ink.pair_words(source,rendered)
 for row in rows:
  row['samples']=[];a,b=row['source'],row['rendered']
  if b is None:row['reason']='no_geometry_pair';continue
  bounds=[math.floor(min(a['bbox'][0],b['bbox'][0]))-1,math.floor(min(a['bbox'][1],b['bbox'][1]))-1,
          math.ceil(max(a['bbox'][2],b['bbox'][2]))+1,math.ceil(max(a['bbox'][3],b['bbox'][3]))+1]
  row['roi_points']=bounds
  if bounds[0]<0 or bounds[1]<0 or bounds[2]>dimensions[0] or bounds[3]>dimensions[1]:row['reason']='outside_page';continue
  if bounds[2]-bounds[0]>250 or bounds[3]-bounds[1]>50:row['reason']='crop_limit';continue
  if any(word is not own and ink.intersects(bounds,word['bbox']) for words,own in ((source,a),(rendered,b)) for word in words):row['reason']='neighbor_intersection'
 return rows


def measurements(ink,source,rendered):
 result=ink.ink_metrics(source,rendered)
 # This diagnostic reports raw observations, not even a per-word pass label.
 result.pop('ink_within_diagnostic_bounds',None)
 if result['status']=='observed':
  result['signed_edges_points']=[(b-a)/ink.SCALE for a,b in zip(result['source_ink_bbox'],result['rendered_ink_bbox'])]
 return result


def sample(ink,images,roi):
 if len({im.size for im in images})!=1:return {'dpi':ink.DPI,'status':'abstain','reason':'pixel_grid_mismatch'}
 box=[int(v*ink.SCALE) for v in roi]
 crops=[image.crop(box) for image in images]
 return {'dpi':ink.DPI,'candidate':measurements(ink,crops[0],crops[1]),'baseline':measurements(ink,crops[0],crops[2])}


def summarize(rows):
 common=[i for i,row in enumerate(rows) if row['exact_text'] and not row.get('reason') and
         tuple(s['dpi'] for s in row['samples'])==DPIS and
         all(s.get(kind,{}).get('status')=='observed' for s in row['samples'] for kind in ('candidate','baseline'))]
 summaries=[]
 for slot,dpi in enumerate(DPIS):
  item={'dpi':dpi,'common_observed_words':len(common)}
  for kind in ('candidate','baseline'):
   item[kind]={metric:statistics.median(rows[i]['samples'][slot][kind][metric] for i in common) if common else None
               for metric in ('ink_edge_error_points','foreground_mae','mask_iou')}
  summaries.append(item)
 return {'common_observed_word_indices':common,'common_observed_words':len(common),'resolution_summary':summaries}


def versions(deadline):
 result={}
 for name in ('pdftotext','pdftoppm'):
  with tempfile.TemporaryFile() as output:
   deadline.run([name,'-v'],stdout=output,stderr=output,check=True,timeout=10)
   if output.tell()>4096:raise ValueError('unexpected renderer version output')
   output.seek(0);result[name]=output.read().decode('utf-8',errors='replace').splitlines()[0]
 return result


def diagnose(source,rendered,baseline,seconds=MAX_SECONDS,_deadline=None):
 deadline=_deadline or Deadline(min(seconds,MAX_SECONDS));paths=[Path(p).resolve() for p in (source,rendered,baseline)]
 tool=load_ink(max(DPIS),deadline)
 pages=[]
 with tempfile.TemporaryDirectory(prefix='smartppt-poppler-multires-') as temp:
  folder=Path(temp)
  labels=('source','rendered','baseline')
  snapshots=[folder/(label+'.pdf') for label in labels]
  hashes={label:copy_and_digest(path,snapshot,tool.MAX_FILE_BYTES,deadline) for label,path,snapshot in zip(labels,paths,snapshots)}
  paths=snapshots # All resolutions read the exact bytes recorded in the hashes.
  refs,preds,bases=[tool.bounded_words(path,folder,label) for path,label in zip(paths,('source','rendered','baseline'))]
  deadline.remaining();tool.validate_pages(refs,preds);tool.validate_pages(refs,bases)
  if any(words for _,words in bases):raise ValueError('source-image baseline must contain zero extractable words')
  engine_versions=versions(deadline)
  for number,((dimensions,ref),(_,pred)) in enumerate(zip(refs,preds),1):
   deadline.remaining();rows=fixed_rows(tool,dimensions,ref,pred)
   for dpi in DPIS:
    deadline.remaining();ink=load_ink(dpi,deadline)
    images=[]
    try:
     for path,label in zip(paths,('source','rendered','baseline')):
      images.append(ink.raster(path,number,folder/label,dimensions))
     for row in rows:
      deadline.remaining()
      if not row.get('reason'):row['samples'].append(sample(ink,images,row['roi_points']))
    finally:
     for image in images:image.close()
   pages.append({'page':number,'source_words':len(ref),'rendered_words':len(pred),'words':rows,**summarize(rows)})
  deadline.remaining()
 return {'diagnostic_only':True,'no_acceptance_verdict':True,'existing_216dpi_results_modified':False,
         'registration':'none','resampling':'none','baseline_error_subtracted':False,
         'roi_policy':'integer-point union bounds, outward rounding plus 1pt; frozen across DPI',
         'dpis':list(DPIS),'input_sha256':hashes,'engine_versions':engine_versions,'pages':pages}


def main():
 parser=argparse.ArgumentParser(description=__doc__)
 for name in ('source','rendered','baseline','output'):parser.add_argument('--'+name,type=Path,required=True)
 args=parser.parse_args()
 if args.output.exists():raise FileExistsError('output already exists')
 deadline=Deadline()
 result=diagnose(args.source,args.rendered,args.baseline,_deadline=deadline)
 deadline.remaining()
 # Exclusive creation also protects against races after the initial existence
 # check. A budget failure removes only this run's incomplete artifact.
 with args.output.open('x') as stream:
  created=os.fstat(stream.fileno())
  try:
   for i,chunk in enumerate(json.JSONEncoder(indent=2).iterencode(result)):
    if i%1024==0:deadline.remaining()
    stream.write(chunk)
   deadline.remaining()
  except BaseException:
   stream.close()
   try:
    current=args.output.stat()
    if (current.st_dev,current.st_ino)==(created.st_dev,created.st_ino):args.output.unlink()
   except FileNotFoundError:pass
   raise

if __name__=='__main__':main()
