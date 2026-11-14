"""Recover one clipped header prefix from an independently ruled header band.

Two-column, black single-line headers only. No numerical corrections, inferred
column semantics, or newly exposed clipped/transparent text. Removed table-exterior
unit text is retained verbatim as explicitly unassociated source context.
"""
from copy import deepcopy
import math,re
import numpy as np
from pdfplumber.utils import extract_text,cluster_objects
from layout_native_order import _box,_geometry,_inside,_overlap,_finite
from layout_tables import physical_page,visible_box
from layout_native_colspans import _covered
from layout_split_rows import black_glyph,visible_glyphs
from source_row_visibility import contribution

def compact(s):return ''.join(s.split())

def visible_rule(image,horizontal,position,start,end,width,height):
    pixels=image if horizontal else image.T
    along=image.shape[1]/width if horizontal else image.shape[0]/height
    across=image.shape[0]/height if horizontal else image.shape[1]/width
    first,last=math.ceil(start*along)+4,math.floor(end*along)-4
    if first<0 or last>pixels.shape[1] or last-first<6:return False
    center=round(position*across)
    for fixed in range(center-2,center+3):
        if fixed<4 or fixed+4>=pixels.shape[0]:continue
        ink=pixels[fixed,first:last].astype('int16')
        background=np.maximum(pixels[fixed-4,first:last],pixels[fixed+4,first:last]).astype('int16')
        if np.mean((ink<200)&(background-ink>=25))>=.95:return True
    return False

def recover(model,page):
    try:return _recover(model,page)
    except (ValueError,TypeError,KeyError,AttributeError,IndexError,OverflowError,OSError,RuntimeError):return model

def _recover(model,page):
    if page.rotation or tuple(page.bbox)!=(0,0,page.width,page.height) or tuple(page.cropbox)!=tuple(page.mediabox):return model
    if 'sourceHeaderContext' in model:return model
    cells=model['cells'];rows=len(model['heights']);cols=len(model['widths'])
    if cols!=2 or not 5<=rows<=100 or len(cells)>200 or len(page.chars)>10000:return model
    if any(not _finite(x) or x<=0 for x in model['widths']+model['heights']):return model
    used=set()
    for c in cells:
        if (not isinstance(c.get('text'),str)or len(c['text'])>2000 or any(type(c.get(k))is not int for k in('r','c','rs','cs'))
            or c['rs']!=1 or c['cs']!=1 or not 0<=c['r']<rows or c['c']not in(0,1)
            or (c['r'],c['c'])in used):return model
        used.add((c['r'],c['c']))
    nonempty=[c for c in cells if c['text'].strip()]
    if any(not _box(c.get('sourceTextCandidate'))for c in nonempty):return model
    heads=sorted((c for c in nonempty if c['r']==0),key=lambda c:c['c'])
    if len(heads)!=2:return model
    left,right=heads;a=left['sourceTextCandidate'];b=right['sourceTextCandidate'];box=model['bbox']
    if not _box(box):return model
    if len(page.edges)>5000 or len(page.curves)>1000 or len(page.rects)>2000:return model
    if sum(len(getattr(page,k,[])or[])for k in('images','annots'))>100:return model
    edges=physical_page(page).edges
    if len(edges)>5000 or len(page.curves)>1000:return model
    horizontals=[e for e in edges if e['orientation']=='h' and abs(e['x0']-box[0])<=3 and abs(e['x1']-box[2])<=3]
    bands=[]
    for group in cluster_objects(horizontals,lambda e:e['top'],1):
        bands.append((sum(e['top']for e in group)/len(group),min(e['x0']for e in group),max(e['x1']for e in group)))
    above=[x for x in bands if a[1]-30<x[0]<a[1]];below=[x for x in bands if a[3]<x[0]<a[3]+10]
    if not above or not below:return model
    top,x0,x1=max(above);bottom,lo,hi=min(below)
    if abs(lo-x0)>.5 or abs(hi-x1)>.5 or not 8<bottom-top<30:return model
    verticals=[e for e in edges if e['orientation']=='v' and x0+20<e['x0']<x1-20 and e['top']<=top+1 and e['bottom']>=bottom-1]
    groups=cluster_objects(verticals,lambda e:e['x0'],1)
    if len(groups)!=1:return model
    split=sum(e['x0']for e in groups[0])/len(groups[0])
    if not _covered(edges,False,split,top,bottom):return model
    header=(x0,top,x1,bottom);view=visible_box(page)
    if not _inside(header,view):return model
    # Four independent complete body records corroborate logical column mapping.
    corroborated=0;anchor_bands=[];anchor_glyphs=[]
    source_chars=[g for g in page.chars if g["text"].strip()]
    if any(not _box(_geometry(g))for g in source_chars):return model
    for r in range(1,rows):
        pair=[c for c in nonempty if c['r']==r]
        if len(pair)!=2:continue
        pair.sort(key=lambda c:c['c'])
        if (pair[0]['sourceTextCandidate'][1]>=bottom and pair[1]['sourceTextCandidate'][1]>=bottom
            and x0<=pair[0]['sourceTextCandidate'][0]<pair[0]['sourceTextCandidate'][2]<split
            and split<pair[1]['sourceTextCandidate'][0]<pair[1]['sourceTextCandidate'][2]<=x1):
            parts=[]
            for cell in pair:
                b0=cell['sourceTextCandidate'];part=[g for g in source_chars if b0[0]<=(g['x0']+g['x1'])/2<=b0[2] and b0[1]<=(g['top']+g['bottom'])/2<=b0[3]]
                if not part or compact(extract_text(part,x_tolerance=2,y_tolerance=3))!=compact(cell['text']):return model
                parts.append(part)
            both=parts[0]+parts[1];band=(min(g['top']for g in both),max(g['bottom']for g in both))
            if max(g['top']for g in both)-band[0]>.1:return model
            if any(band[0]<old[1] and band[1]>old[0]for old in anchor_bands):return model
            anchor_bands.append(band);anchor_glyphs.extend(both);corroborated+=1
        else:return model
    if corroborated<4:return model
    chars=[g for g in page.chars if g['text'].strip()]
    if any(not _box(_geometry(g))for g in chars):return model
    glyphs=[g for g in chars if _overlap(_geometry(g),header)]
    if not glyphs or any(not _inside(_geometry(g),header)for g in glyphs):return model
    lgs=[g for g in glyphs if g['x1']<split];rgs=[g for g in glyphs if g['x0']>split]
    if len(lgs)+len(rgs)!=len(glyphs)or not lgs or not rgs:return model
    if compact(extract_text(lgs,x_tolerance=2,y_tolerance=3))!=compact(left['text']):return model
    # The old mixed header must be exactly an outside unit plus an actual suffix.
    extra=[g for g in chars if b[0]<=(g['x0']+g['x1'])/2<=b[2] and b[1]<=(g['top']+g['bottom'])/2<=b[3] and g['bottom']<top]
    if not extra:return model
    unit=extract_text(extra,x_tolerance=2,y_tolerance=3).strip()
    if not re.fullmatch(r'\([^()\n]{1,20}\)',unit):return model
    def owns(b0,g):return b0[0]<=(g['x0']+g['x1'])/2<=b0[2] and b0[1]<=(g['top']+g['bottom'])/2<=b0[3]
    if any(not owns(a,g)for g in lgs)or any(owns(a,g)for g in rgs+extra):return model
    selected=[g for g in chars if owns(b,g)]
    if compact(extract_text(selected,x_tolerance=2,y_tolerance=3))!=compact(right['text']):return model
    old=compact(right['text']);prefix=compact(unit)
    if not old.startswith(prefix):return model
    suffix=old[len(prefix):];text=extract_text(rgs,x_tolerance=2,y_tolerance=3).strip();new=compact(text)
    if not suffix or not new.endswith(suffix)or new==suffix:return model
    missing=new[:-len(suffix)]
    if not re.fullmatch('[A-Za-z]{1,30}',missing):return model
    allg=glyphs+extra
    if len(allg)>300 or len(anchor_glyphs)>1000:return model
    if any(not black_glyph(g)or not g.get('upright')or not _inside(_geometry(g),view)
           or len(g.get('matrix',()))!=6 or not all(_finite(v)for v in g['matrix'])
           or g['matrix'][0]<=0 or g['matrix'][3]<=0 or abs(g['matrix'][1])>.001 or abs(g['matrix'][2])>.001 for g in allg):return model
    for line in (lgs,rgs,extra):
        if max(g['top']for g in line)-min(g['top']for g in line)>.1:return model
        if any(not isinstance(g.get('fontname'),str)or not g['fontname']for g in line):return model
        if len({g['fontname']for g in line})!=1:return model
        if max(g['height']for g in line)-min(g['height']for g in line)>.1:return model
        ordered=sorted(line,key=lambda g:g['x0'])
        if line is not extra and any(u['x1']>v['x0']+.02 for u,v in zip(ordered,ordered[1:])):return model
    if any(c not in heads and any(c['sourceTextCandidate'][0]<=(g['x0']+g['x1'])/2<=c['sourceTextCandidate'][2] and c['sourceTextCandidate'][1]<=(g['top']+g['bottom'])/2<=c['sourceTextCandidate'][3] for g in allg)for c in nonempty):return model
    obstacles=[_geometry(o)for kind in('images','annots')for o in(getattr(page,kind,[])or[])]
    obstacles += [_geometry(o)for o in page.rects+page.curves if o.get('fill') and o.get('width',0)>2 and o.get('height',0)>2]
    for e in page.edges+page.curves:
        width=e.get('linewidth',0)
        if not _finite(width)or not 0<=width<=100:return model
        q=_geometry(e);pad=width*10+.05;obstacles.append((q[0]-pad,q[1]-pad,q[2]+pad,q[3]+pad))
    if len(allg)*len(obstacles)+len(allg)*len(nonempty)+len(source_chars)*len(nonempty)>2_000_000:return model
    if any(_overlap(_geometry(g),o)for g in allg for o in obstacles):return model
    evidence=contribution(page)
    if evidence is None:return model
    image,mask=evidence
    if not visible_glyphs(mask,allg+anchor_glyphs,page.width,page.height):return model
    if not all(visible_rule(image,h,pos,start,end,page.width,page.height)for h,pos,start,end in[(True,top,x0,x1),(True,bottom,x0,x1),(False,split,top,bottom)]):return model
    result=deepcopy(model);target=next(c for c in result['cells']if c['r']==0 and c['c']==1)
    target['text']=text;target['sourceTextCandidate']=[min(g['x0']for g in rgs),min(g['top']for g in rgs),max(g['x1']for g in rgs),max(g['bottom']for g in rgs)]
    for key in('sourceTextBox','sourceFont','glyphWidths'):target.pop(key,None)
    result['sourceHeaderContext']=unit
    return result
