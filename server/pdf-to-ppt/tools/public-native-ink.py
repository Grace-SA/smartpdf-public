"""Independent ink-only diagnostic; no correctness or production-readiness verdict.

Fixed Poppler raster grid, geometry-only pairing, no image registration.
Abstentions remain unknown; original strict font-box results are never changed.
Ink thresholds are descriptive diagnostics, not conversion acceptance gates.
Font descriptor ascenders/descenders may cover more accented glyphs than a PDF
subset, changing parser boxes without moving ink. That explains some differences;
it is not permission to shrink font metrics or waive strict-box failures."""
import math,subprocess,json,importlib.util,tempfile,os
from collections import Counter
from pathlib import Path
import numpy as np
from PIL import Image
DPI=216
SCALE=DPI/72

def intersects(a,b):return a[0]<b[2] and b[0]<a[2] and a[1]<b[3] and b[1]<a[3]

def ink_metrics(a,b):
 av=np.asarray(a.convert('RGB'),dtype=float);bv=np.asarray(b.convert('RGB'),dtype=float)
 if av.shape!=bv.shape:return {'status':'abstain','reason':'different_shape'}
 borders=[np.concatenate((v[0],v[-1],v[:,0],v[:,-1])) for v in (av,bv)]
 bg=[np.median(border,axis=0) for border in borders]
 if any(np.max(np.abs(border-color))>12 for border,color in zip(borders,bg)) or np.max(np.abs(bg[0]-bg[1]))>12:
  return {'status':'abstain','reason':'non_solid_border'}
 masks=[np.max(np.abs(v-color),axis=2)>30 for v,color in zip((av,bv),bg)]
 if not all(mask.any() for mask in masks):return {'status':'abstain','reason':'empty_ink'}
 def box(mask):
  ys,xs=np.where(mask);return [int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)]
 boxes=[box(m) for m in masks];edge=max(abs(x-y) for x,y in zip(*boxes))/SCALE
 union=masks[0]|masks[1]
 error=float(np.abs(av-bv)[union].mean()/255)
 return {'status':'observed','source_ink_bbox':boxes[0],'rendered_ink_bbox':boxes[1],'ink_edge_error_points':edge,'foreground_mae':error,'mask_iou':float((masks[0]&masks[1]).sum()/union.sum()),'ink_within_diagnostic_bounds':edge<=.5 and error<=.16}

def measure(source,rendered,row,source_words,rendered_words):
 if source.size!=rendered.size:return {'status':'abstain','reason':'different_page_pixel_dimensions'}
 s,p=row['source'],row['rendered']
 if not p:return {'status':'abstain','reason':'no_geometry_pair'}
 union=[min(s['bbox'][0],p['bbox'][0]),min(s['bbox'][1],p['bbox'][1]),max(s['bbox'][2],p['bbox'][2]),max(s['bbox'][3],p['bbox'][3])]
 crop=[math.floor(union[0]*SCALE)-2,math.floor(union[1]*SCALE)-2,math.ceil(union[2]*SCALE)+2,math.ceil(union[3]*SCALE)+2]
 if crop[0]<0 or crop[1]<0 or crop[2]>source.width or crop[3]>source.height:return {'status':'abstain','reason':'outside_page'}
 if crop[2]-crop[0]>1500 or crop[3]-crop[1]>300:return {'status':'abstain','reason':'unbounded_crop'}
 points=[v/SCALE for v in crop]
 for words,own in ((source_words,s),(rendered_words,p)):
  if any(w is not own and intersects(points,w['bbox']) for w in words):return {'status':'abstain','reason':'neighbor_box_intersection'}
 result=ink_metrics(source.crop(crop),rendered.crop(crop))
 if result['status']=='observed':
  result['ink_within_diagnostic_bounds']=bool(row['exact_text'] and result['ink_within_diagnostic_bounds'])
  result['crop_pixels']=crop
 return result

MAX_PAGES=20
MAX_PIXELS=20_000_000
MAX_DIMENSION=10000
MAX_WORDS=2000
MAX_FILE_BYTES=64*1024*1024
MAX_XML_BYTES=8*1024*1024


def comparator():
 spec=importlib.util.spec_from_file_location('public_native_compare',Path(__file__).with_name('public-native-compare.py'))
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 return module


def extraction_limit():
 if os.name!='posix':raise RuntimeError('bounded PDF text extraction requires POSIX file-size limits')
 try:
  import resource
  resource.RLIMIT_FSIZE
 except (ImportError,AttributeError) as error:
  raise RuntimeError('bounded PDF text extraction requires RLIMIT_FSIZE') from error
 def limit():
  # Only the child receives this limit, including its redirected stderr file.
  resource.setrlimit(resource.RLIMIT_FSIZE,(MAX_XML_BYTES+1,MAX_XML_BYTES+1))
 return limit


def bounded_words(path,folder,label):
 limit=extraction_limit();xml_path=folder/(label+'-words.xml');error_path=folder/(label+'-words.stderr')
 with xml_path.open('wb') as output,error_path.open('wb') as error:
  subprocess.run(['pdftotext','-f','1','-l',str(MAX_PAGES+1),'-bbox-layout','-enc','UTF-8',str(path),'-'],stdout=output,stderr=error,check=True,timeout=60,preexec_fn=limit)
 if xml_path.stat().st_size>MAX_XML_BYTES:raise ValueError('XML byte resource bound exceeded')
 # Same XML interpretation as the sibling strict comparator; only extraction
 # differs. Never call its unbounded whole-document stdout capture here.
 module=comparator();document=module.E.fromstring(xml_path.read_bytes());pages=[]
 for page in document.iter():
  if not page.tag.endswith('}page'):continue
  words=[]
  for word in page.iter():
   if word.tag.endswith('}word'):
    words.append({'text':''.join(word.itertext()),'bbox':[float(word.get(k)) for k in ('xMin','yMin','xMax','yMax')]})
  pages.append(((float(page.get('width')),float(page.get('height'))),words))
 return pages


def validate_pages(source,rendered):
 if not source or len(source)!=len(rendered):raise ValueError('page count mismatch or empty PDF')
 if len(source)>MAX_PAGES:raise ValueError('page count resource bound exceeded')
 for (sd,sw),(rd,rw) in zip(source,rendered):
  if not all(math.isfinite(x) and x>0 for x in (*sd,*rd)):raise ValueError('invalid page dimensions')
  if max(abs(x-y) for x,y in zip(sd,rd))>.01:raise ValueError('page dimensions differ')
  for dimensions in (sd,rd):
   size=[math.ceil(x*SCALE) for x in dimensions]
   if max(size)>MAX_DIMENSION or size[0]*size[1]>MAX_PIXELS:raise ValueError('page pixel resource bound exceeded')
  for words in (sw,rw):
   if len(words)>MAX_WORDS:raise ValueError('word count resource bound exceeded')
   if any(len(w['bbox'])!=4 or not all(math.isfinite(v) for v in w['bbox']) or w['bbox'][2]<=w['bbox'][0] or w['bbox'][3]<=w['bbox'][1] for w in words):raise ValueError('invalid word box')


def pair_words(source,rendered):
 # Same geometry-only mutual-nearest rule as the independent bbox diagnostic.
 # Do not choose another occurrence because its text happens to match.
 def nearest(word,words):
  if not words:return None
  def center(w):l,t,r,b=w['bbox'];return ((l+r)/2,(t+b)/2)
  c=center(word);distances=[math.dist(c,center(w)) for w in words];best=min(distances)
  return distances.index(best) if distances.count(best)==1 else None
 import unicodedata
 forward=[nearest(w,rendered) for w in source];back=[nearest(w,source) for w in rendered]
 rows=[]
 for i,word in enumerate(source):
  j=forward[i];other=rendered[j] if j is not None and back[j]==i else None
  exact=other is not None and unicodedata.normalize('NFKC',word['text'])==unicodedata.normalize('NFKC',other['text'])
  rows.append({'source':word,'rendered':other,'exact_text':exact})
 return rows


def raster(path,number,prefix,dimensions):
 subprocess.run(['pdftoppm','-r',str(DPI),'-f',str(number),'-l',str(number),'-singlefile','-png',str(path),str(prefix)],check=True,timeout=60,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
 with Image.open(str(prefix)+'.png') as image:
  if image.width*image.height>MAX_PIXELS or max(image.size)>MAX_DIMENSION:raise ValueError('rendered pixel resource bound exceeded')
  expected=[math.ceil(x*SCALE) for x in dimensions]
  if any(abs(a-b)>1 for a,b in zip(image.size,expected)):raise ValueError('unexpected rendered page dimensions')
  return image.convert('RGB').copy()


def diagnose(source,rendered):
 source,rendered=Path(source).resolve(),Path(rendered).resolve()
 if any(p.stat().st_size>MAX_FILE_BYTES for p in (source,rendered)):raise ValueError('input file resource bound exceeded')
 pages=[]
 with tempfile.TemporaryDirectory(prefix='smartppt-poppler-ink-') as temp:
  folder=Path(temp)
  references=bounded_words(source,folder,'source');predictions=bounded_words(rendered,folder,'rendered')
  validate_pages(references,predictions)
  for n,((dimensions,ref),(_,pred)) in enumerate(zip(references,predictions),1):
   a=raster(source,n,folder/'source',dimensions);b=raster(rendered,n,folder/'rendered',dimensions)
   if a.size!=b.size:
    pages.append({'page':n,'source_words':len(ref),'rendered_words':len(pred),'status':'abstain','reason':'different_page_pixel_dimensions','source_pixels':list(a.size),'rendered_pixels':list(b.size),'ink_within_diagnostic_bounds':0,'words':[]})
    continue
   rows=pair_words(ref,pred)
   for row in rows:row['ink']=measure(a,b,row,ref,pred)
   counts=Counter(row['ink'].get('reason','observed') for row in rows)
   pages.append({'page':n,'source_words':len(ref),'rendered_words':len(pred),'counts':dict(counts),'ink_within_diagnostic_bounds':sum(row['ink'].get('ink_within_diagnostic_bounds',False) for row in rows),'words':rows})
 return {'diagnostic_only':True,'no_acceptance_verdict':True,'strict_bbox_results_modified':False,'reference':'Independent Poppler fixed-grid raster; not human ground truth','dpi':DPI,'registration':'none','bounds':{'ink_edge_points':.5,'foreground_mae':.16},'pages':pages}


def main():
 import argparse
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--source',type=Path,required=True)
 parser.add_argument('--rendered',type=Path,required=True)
 parser.add_argument('--output',type=Path,required=True)
 args=parser.parse_args()
 if args.output.exists():raise FileExistsError('output already exists')
 result=diagnose(args.source,args.rendered)
 with args.output.open('x') as f:json.dump(result,f,indent=2)

if __name__=='__main__':main()
