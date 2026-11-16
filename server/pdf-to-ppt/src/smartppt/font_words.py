from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont

def rank_words(text,crop,background,directory,candidates):
 words=text.split()
 if not 1<=len(words)<=60:return []
 pixels=np.asarray(crop,dtype=float);ink=np.max(np.abs(pixels-np.asarray(background)),axis=2);ink/=max(1,ink.max())
 binary=ink>.5;pad=np.pad(binary.astype(np.uint8),1);near=sum(pad[y:y+binary.shape[0],x:x+binary.shape[1]] for y in range(3) for x in range(3));binary&=near>=3
 columns=binary.any(axis=0);occupied=np.flatnonzero(columns)
 if not len(occupied):return []
 spans=[];start=None
 for x in range(int(occupied[0]),int(occupied[-1])+1):
  if not columns[x] and start is None:start=x
  elif columns[x] and start is not None:spans.append((start,x));start=None
 if len(spans)<len(words)-1:return []
 gaps=sorted(spans,key=lambda b:b[1]-b[0],reverse=True)[:len(words)-1]
 others=[b[1]-b[0] for b in spans if b not in gaps]
 if gaps and others and min(b-a for a,b in gaps)<max(2,np.median(others)*1.5):return []
 cuts=[0]+[int((a+b)/2) for a,b in sorted(gaps)]+[crop.width];samples=[]
 for word,l,r in zip(words,cuts,cuts[1:]):
  points=np.argwhere(binary[:,l:r])
  if not len(points):return []
  t,b=points[:,0].min(),points[:,0].max()+1;x,xx=l+points[:,1].min(),l+points[:,1].max()+1
  samples.append((word,ink[t:b,x:xx]))
 ranked=[]
 for family,filename,bold,italic in candidates:
  path=Path(directory)/filename
  if not path.is_file():continue
  font=ImageFont.truetype(str(path),80);error=weight=0
  for word,sample in samples:
   l,t,r,b=font.getbbox(word)
   if r-l<=0 or b-t<=0:return []
   mask=Image.new('L',(r-l,b-t));ImageDraw.Draw(mask).text((-l,-t),word,font=font,fill=255);bounds=mask.getbbox()
   if not bounds:return []
   mask=mask.crop(bounds).resize((sample.shape[1],sample.shape[0]),Image.Resampling.LANCZOS)
   error+=float(np.abs(sample-np.asarray(mask)/255).mean())*len(word);weight+=len(word)
  ranked.append({'family':family,'bold':bold,'italic':italic,'path':str(path),'error':error/weight,'matched':False})
 return sorted(ranked,key=lambda r:r['error'])
