"""Trim only excessive vertical detection padding at a proven empty row."""
from copy import deepcopy
import numpy as np
from .consensus import erase_bounds,line_bounds


def trim_line_padding(image,lines):
    refined=deepcopy(lines);pixels=np.asarray(image);changed=set()
    for i,line in enumerate(refined):
        for j in range(i):
            first,second=refined[j],line
            a,b=line_bounds(first),line_bounds(second)
            if a[1]+a[3]>b[1]+b[3]:first,second=second,first;a,b=b,a
            # Vertical/slanted detections and separate columns keep their boxes.
            if any(abs(x['polygon'][0][1]-x['polygon'][1][1])>1 or abs(x['polygon'][2][1]-x['polygon'][3][1])>1 for x in [first,second]):continue
            if min(a[2],b[2])-max(a[0],b[0])<min(a[2]-a[0],b[2]-b[0])*.5:continue
            cy1,cy2=(a[1]+a[3])/2,(b[1]+b[3])/2
            if cy2-cy1<min(a[3]-a[1],b[3]-b[1])*.25:continue
            left=max(0,int(np.floor(min(a[0],b[0])))-1);right=min(pixels.shape[1],int(np.ceil(max(a[2],b[2])))+2)
            top=max(1,int(np.ceil(max(a[1],b[1],cy1)))+1);bottom=min(pixels.shape[0]-2,int(np.floor(min(a[3],b[3],cy2)))-1)
            candidates=[]
            for y in range(top,bottom+1):
                stripe=pixels[y-1:y+2,left:right].astype(float)
                if not stripe.size:continue
                paper=np.median(stripe.reshape(-1,3),axis=0)
                if paper.min()>=180 and np.max(np.abs(stripe-paper))<=12:candidates.append(y)
            if not candidates:continue
            cut=min(candidates,key=lambda y:abs(y-(cy1+cy2)/2))
            for point in first['polygon'][2:]:point[1]=min(point[1],cut)
            for point in second['polygon'][:2]:point[1]=max(point[1],cut+1)
            changed.update((i,j))
    return refined,sorted(changed)


def extend_tight_padding(image,lines):
    """Extend an upright tight detection by at most two pixels to an empty ring.

    All proposed erase boxes participate in ordinary overlap checks afterwards.
    Text, confidence and the original record stay unchanged.
    """
    refined=deepcopy(lines);pixels=np.asarray(image);changed=[]
    for i,line in enumerate(refined):
        p=line['polygon']
        if not (p[0][1]==p[1][1] and p[2][1]==p[3][1] and
                p[0][0]==p[3][0] and p[1][0]==p[2][0] and
                p[0][0]<p[1][0] and p[0][1]<p[3][1]):continue
        l,t,r,b=erase_bounds(line)
        if l<0 or t<0 or r>pixels.shape[1] or b>pixels.shape[0] or r-l<2 or b-t<2:continue
        crop=pixels[t:b,l:r];border=np.concatenate((crop[0],crop[-1],crop[:,0],crop[:,-1])).astype(float)
        if np.quantile(np.abs(border-np.median(border,axis=0)),.95)<=12:continue
        for extra in (1,2):
            left,top,right,bottom=l-extra,t-extra,r+extra,b+extra
            if left<0 or top<0 or right>pixels.shape[1] or bottom>pixels.shape[0]:continue
            crop=pixels[top:bottom,left:right]
            border=np.concatenate((crop[0],crop[-1],crop[:,0],crop[:,-1])).astype(float)
            if np.max(np.abs(border-np.median(border,axis=0)))>12:continue
            line['polygon']=[[left+1,top+1],[right-1,top+1],[right-1,bottom-1],[left+1,bottom-1]]
            changed.append(i);break
    return refined,changed
