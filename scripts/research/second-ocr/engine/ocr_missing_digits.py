"""Recover a missed isolated digit only from exact local glyph/recognition evidence."""
import math
import re
from collections import defaultdict,Counter

import cv2
import numpy as np


def glyph(image, box, scale, masks=None):
    """One complete, contrasted component inside a grid cell, without resampling."""
    pad=max(1,round(scale))
    x0,y0,x1,y1=box
    if masks is not None:
        # Check the discarded inner edge band too. Only pixels belonging to
        # proved long grid rules may be omitted, never short extra ink.
        a,b,c,d=math.ceil(x0)+1,math.ceil(y0)+1,math.floor(x1),math.floor(y1)
        if a<0 or b<0 or c>image.shape[1] or d>image.shape[0] or a>=c or b>=d:return None
        full=cv2.cvtColor(image[b:d,a:c],cv2.COLOR_RGB2GRAY)
        band=np.ones(full.shape,dtype=bool)
        # Mark exactly the crop rectangle, using its asymmetric exclusive
        # right/bottom bounds, rather than an approximate symmetric margin.
        left=max(0,math.ceil(x0)+pad)-a;top=max(0,math.ceil(y0)+pad)-b
        right=min(image.shape[1],math.floor(x1)-pad)-a
        bottom=min(image.shape[0],math.floor(y1)-pad)-b
        if 0<=left<right<=full.shape[1] and 0<=top<bottom<=full.shape[0]:
            band[top:bottom,left:right]=False
        rules=(masks[0][b:d,a:c]>0)|(masks[1][b:d,a:c]>0)
        if np.any(band & (full<245) & ~rules):return None
    x0,y0=max(0,math.ceil(x0)+pad),max(0,math.ceil(y0)+pad)
    x1,y1=min(image.shape[1],math.floor(x1)-pad),min(image.shape[0],math.floor(y1)-pad)
    if x1<=x0 or y1<=y0 or (x1-x0)*(y1-y0)>100000:
        return None
    crop=image[y0:y1,x0:x1]
    gray=cv2.cvtColor(crop,cv2.COLOR_RGB2GRAY)
    if int(gray.max())-int(gray.min())<80 or gray.min()>160:
        return None
    _,ink=cv2.threshold(gray,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
    n,_,stats,_=cv2.connectedComponentsWithStats(ink)
    # Every foreground component counts, including noise and punctuation.
    if n!=2:
        return None
    x,y,w,h,area=map(int,stats[1])
    if (not 8<=h<=48 or not 3<=w<=36 or w>h*1.3 or area<12
            or area>w*h*.8 or x<2 or y<2 or x+w+2>gray.shape[1] or y+h+2>gray.shape[0]):
        return None
    patch=gray[y-2:y+h+2,x-2:x+w+2]
    ring=patch.copy();ring[2:-2,2:-2]=255
    if ring.min()<245:return None
    return (w,h,patch.tobytes()),(x0+x,y0+y,x0+x+w,y0+y+h),(x0,y0,x1,y1)


def closed(box, masks, scale):
    if masks is None:return False
    horizontal,vertical=masks;left,top,right,bottom=map(int,box);pad=max(1,round(scale));trim=max(2,round(scale*1.5))
    if right-left<=trim*2 or bottom-top<=trim*2:return False
    for y in (top,bottom):
        sample=horizontal[max(0,y-pad):y+pad+1,left+trim:right-trim]
        if not sample.size or (sample>0).any(axis=0).mean()<.95:return False
    for x in (left,right):
        sample=vertical[top+trim:bottom-trim,max(0,x-pad):x+pad+1]
        if not sample.size or (sample>0).any(axis=1).mean()<.95:return False
    return True


def recover(image, entries, boxes, reader, scale, budget, masks=None):
    """Never replace existing text; page budget limits candidates and raster work."""
    from second_ocr import enabled
    if not enabled():
        return entries,0
    if len(entries)!=len(boxes) or not hasattr(reader,'text_rec'):
        return entries,0
    references=defaultdict(lambda:defaultdict(list));shapes={}
    duplicates={b for b,n in Counter(boxes).items() if n>1}
    for i,(cell,box) in enumerate(zip(entries,boxes)):
        if cell['rs']!=1 or cell['cs']!=1 or box in duplicates or not closed(box,masks,scale):
            continue
        text=cell['text'];score=cell.get('confidence',0)
        if text and len(text)>16:
            continue
        area=max(0,box[2]-box[0])*max(0,box[3]-box[1])
        if budget['pixels']+area>2_000_000:
            continue
        budget['pixels']+=area
        shape=glyph(image,box,scale,masks)
        if shape is None:
            continue
        shapes[i]=shape
        if text:
            references[(cell['c'],box[0],box[2],shape[0])][text].append((cell['r'],i,score))
    candidates=[];crops=[]
    for i,cell in enumerate(entries):
        if cell['text'] or i not in shapes or budget['candidates']>=4:
            continue
        key,ink,interior=shapes[i];labels=references.get((cell['c'],boxes[i][0],boxes[i][2],key),{})
        if len(labels)!=1:
            continue
        expected,refs=next(iter(labels.items()))
        refs=[r for r in refs if isinstance(r[2],(float,int)) and math.isfinite(r[2]) and .98<=r[2]<=1]
        if not re.fullmatch('[0-9]',expected) or len(set(r[0]for r in refs))<2:
            continue
        x0,y0,x1,y1=ink;left,top,right,bottom=interior
        pair=[]
        for fraction in (.2,.4):
            pad=max(2,round((y1-y0)*fraction))
            pair.append(image[max(top,y0-pad):min(bottom,y1+pad),max(left,x0-pad):min(right,x1+pad)])
        if pair[0].shape==pair[1].shape:
            continue
        budget['candidates']+=1;candidates.append((i,expected,[r[1] for r in refs[:2]]));crops.extend(pair)
    if not candidates:
        return entries,0
    try:
        recognized,_=reader.text_rec(crops)
    except (RuntimeError,ValueError,TypeError,IndexError,OverflowError,OSError):
        return entries,0
    if recognized is None or len(recognized)!=len(crops):
        return entries,0
    out=list(entries);count=0
    for j,(i,expected,refs) in enumerate(candidates):
        pair=recognized[j*2:j*2+2]
        if all(isinstance(v,(list,tuple)) and len(v)>=2 and isinstance(v[0],str)
               and v[0].strip()==expected and isinstance(v[1],(int,float))
               and math.isfinite(v[1]) and .98<=v[1]<=1 for v in pair):
            from second_ocr import recognize
            confirmed=True
            for source in [i]+refs:
                _,(a,b,c,d),_=shapes[source]
                result=recognize(image[b-2:d+2,a-2:c+2])
                if result is None:return entries,0
                if (len(result)!=1 or result[0][0]!=expected or not isinstance(result[0][1],(int,float))
                        or not math.isfinite(result[0][1]) or not 90<=result[0][1]<=100):
                    confirmed=False;break
            if confirmed:
                out[i]=dict(entries[i],text=expected,confidence=min(float(v[1])for v in pair));count+=1
    return out,count
