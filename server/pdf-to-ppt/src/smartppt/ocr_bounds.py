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
