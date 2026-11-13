"""Research-only ruled-grid probe. Never imported by application code.

No reference labels are accepted by inference. It is NOT a production OCR engine.
"""
import csv
import subprocess
import time
from pathlib import Path
import cv2
import numpy as np

def lines(a,axis):
 sums=(a>0).sum(axis=axis)
 idx=np.where(sums>0.6*sums.max())[0] if sums.max()>50 else []
 groups=[]
 for i in idx:
  if not groups or i>groups[-1][-1]+1: groups.append([int(i)])
  else: groups[-1].append(int(i))
 return [int(round(np.mean(g))) for g in groups]
def infer(image,tsv,output_dir):
 ROOT=Path(output_dir)
 start=time.monotonic()
 a=cv2.imread(str(image),0)
 if a is None or a.size>16000000:return {'status':'invalid_or_oversized_image'}
 bw=cv2.threshold(a,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)[1]
 h=cv2.morphologyEx(bw,cv2.MORPH_OPEN,np.ones((1,max(40,a.shape[1]//30)),np.uint8))
 v=cv2.morphologyEx(bw,cv2.MORPH_OPEN,np.ones((max(40,a.shape[0]//30),1),np.uint8))
 xs,ys=lines(v,0),lines(h,1)
 if len(xs)<3 or len(ys)<3: return {'status':'no_rectangular_grid','xs':xs,'ys':ys}
 if (len(xs)-1)*(len(ys)-1)>200:return {'status':'cell_budget_exceeded'}
 if min(np.diff(xs))<8 or min(np.diff(ys))<8:return {'status':'degenerate_cells'}
 # Require each full grid boundary, reject missing spans instead of fabricating cells.
 for x in xs:
  if (v[ys[0]:ys[-1]+1,max(0,x-2):x+3]>0).any(axis=1).mean()<.995:return {'status':'incomplete_vertical_grid'}
 for y in ys:
  if (h[max(0,y-2):y+3,xs[0]:xs[-1]+1]>0).any(axis=0).mean()<.995:return {'status':'incomplete_horizontal_grid'}
 buckets=[[[] for _ in xs[:-1]] for _ in ys[:-1]];outside=[]
 if Path(tsv).stat().st_size>10000000:return {'status':'tsv_budget_exceeded'}
 for t in csv.DictReader(Path(tsv).read_text().splitlines(),delimiter='\t'):
  if t['level']!='5' or not t['text'].strip():continue
  x,y,w,z=[int(t[k]) for k in ['left','top','width','height']]
  cols=[i for i in range(len(xs)-1) if xs[i]<x and x+w<xs[i+1]]
  rows=[j for j in range(len(ys)-1) if ys[j]<y and y+z<ys[j+1]]
  if len(cols)!=1 or len(rows)!=1:outside.append(t['text']);continue
  buckets[rows[0]][cols[0]].append((y,x,z,t['text']))
 def ordered(words):
  # Cluster vertically overlapping word boxes before left-to-right sorting.
  lines=[]
  for word in sorted(words):
   y,x,height,text=word
   matches=[line for line in lines if min(line['bottom'],y+height)-max(line['top'],y)>0.5*min(line['bottom']-line['top'],height)]
   if matches:
    line=matches[0];line['words'].append(word);line['top']=min(line['top'],y);line['bottom']=max(line['bottom'],y+height)
   else:lines.append({'top':y,'bottom':y+height,'words':[word]})
  return ' '.join(w[3] for line in sorted(lines,key=lambda l:l['top']) for w in sorted(line['words'],key=lambda w:w[1]))
 cells=[[ordered(b) for b in row] for row in buckets]
 # Evaluate per-cell recognizer separately; never hide baseline failure.
 crop_cells=[]
 for ri,(y0,y1) in enumerate(zip(ys,ys[1:])):
  row=[]
  for ci,(x0,x1) in enumerate(zip(xs,xs[1:])):
   if time.monotonic()-start>45:return {'status':'page_budget_exceeded'}
   crop=a[y0+3:y1-3,x0+3:x1-3]
   crop=cv2.copyMakeBorder(crop,12,12,12,12,cv2.BORDER_CONSTANT,value=255)
   path=ROOT/(Path(image).stem+f'-cell-{ri}-{ci}.png');cv2.imwrite(str(path),crop)
   run=subprocess.run(['tesseract',str(path),'stdout','-l','eng','--psm','6'],capture_output=True,text=True,check=True,timeout=10)
   row.append(' '.join(run.stdout.split()))
  crop_cells.append(row)
 return {'status':'grid','xs':xs,'ys':ys,'cells':cells,'cell_crop_cells':crop_cells,'unassigned':outside}
