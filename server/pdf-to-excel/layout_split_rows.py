"""Join adjacent inferred rows only with complete same-line physical-row proof."""
from collections import Counter
from copy import deepcopy
from itertools import accumulate
import math
from pdfplumber.utils import extract_text
from layout_tables import physical_page, visible_box
from layout_nested_guard import closed_table
from layout_native_order import _box, _geometry, _inside, _overlap, _finite
import numpy as np
from layout_body_rowspans import closed_side


def compact(text):
    return ''.join(text.split())


def recover(model, native, page):
    try:
        return _recover(model, native, page)
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, OverflowError, OSError, RuntimeError, ImportError):
        return model


def _recover(model, native, page):
    if (getattr(page,'rotation',0) or tuple(page.bbox)!=(0,0,page.width,page.height)
            or tuple(page.cropbox)!=tuple(page.mediabox)) : return model
    work=0
    def spend(count):
        nonlocal work
        work+=count
        if work>2_000_000:raise ValueError('Recovery work budget')
    rows,cols=len(model['heights']),len(model['widths']);cells=model['cells']
    if not 3<=rows<=300 or not 2<=cols<=30 or len(cells)>9000 or len(page.chars)>50000:return model
    if len(page.chars)*len(cells)>2_000_000 or len(native)>100 or sum(len(t.get('cells',[])) for t in native)>9000:return model
    if any(not _finite(v) or v<=0 for v in model['heights']+model['widths']):return model
    if any(not isinstance(c.get('text'),str) or any(type(c.get(k)) is not int for k in ('r','c','rs','cs'))
           or not 0<=c['r']<c['r']+c['rs']<=rows or not 0<=c['c']<c['c']+c['cs']<=cols for c in cells):return model
    occupied=set()
    for c in cells:
        slots={(r,col) for r in range(c['r'],c['r']+c['rs']) for col in range(c['c'],c['c']+c['cs'])}
        if occupied&slots:return model
        occupied.update(slots)
    nonempty=[c for c in cells if c['text'].strip()]
    if any(not _box(c.get('sourceTextCandidate')) for c in nonempty):return model
    chars=[g for g in page.chars if g['text'].strip()]
    if any(not _box(_geometry(g)) for g in chars):return model
    view=visible_box(page);edges=physical_page(page).edges
    if len(edges)>10000:return model
    rendered=None
    paint=[]
    for edge in page.edges:
        width=edge.get('linewidth',0)
        if not _finite(width) or not 0<=width<=100:return model
        x0,y0,x1,y1=_geometry(edge);pad=width/2+.5
        box=(x0-pad,y0-pad,x1+pad,y1+pad)
        if not _box(box):return model
        paint.append(box)
    for curve in page.curves:
        width=curve.get('linewidth',0)
        if not _finite(width) or not 0<=width<=100:return model
        x0,y0,x1,y1=_geometry(curve);pad=width*10+.5
        paint.append((x0-pad,y0-pad,x1+pad,y1+pad))
    obstacles=[_geometry(o) for kind in ('images','annots') for o in (getattr(page,kind,[]) or [])]
    if any(not _box(b) for b in obstacles):return model
    # Do not reason through filled shapes or curves that may conceal text/rules.
    obstacles += [_geometry(o) for o in page.rects+page.curves if o.get('fill') and o.get('width',0)>3 and o.get('height',0)>3]
    if any(not _box(b) for b in obstacles):return model
    native_rows=[]
    for table in native:
        if not closed_table(table):continue
        xs=list(accumulate(table['widths'],initial=table['bbox'][0]));ys=list(accumulate(table['heights'],initial=table['bbox'][1]))
        spend(len(table['heights'])*len(table['cells']))
        for r in range(len(table['heights'])):
            source=[c for c in table['cells'] if c['r']<=r<c['r']+c['rs']]
            if any(c['rs']!=1 for c in source):continue
            boxes=[(xs[c['c']],ys[r],xs[c['c']+c['cs']],ys[r+1]) for c in source]
            native_rows.append((source,boxes,(xs[0],ys[r],xs[-1],ys[r+1])))
    if len(native_rows)*len(cells)>500_000:return model
    joins=[]
    for row in range(rows-1):
        spend(len(cells))
        band=[c for c in cells if c['r']<row+2 and c['r']+c['rs']>row]
        active=[c for c in band if c['text'].strip()]
        if any(c['rs']!=1 or (not c['text'].strip() and c['cs']!=1) for c in band) or not {c['r'] for c in active}=={row,row+1}:continue
        slots=[x for c in active for x in range(c['c'],c['c']+c['cs'])]
        if len(set(slots))!=len(slots) or not 2<=len(active)<=cols:continue
        # A shared line, not two text lines in an unruled physical container.
        top=max(c['sourceTextCandidate'][1] for c in active);bottom=min(c['sourceTextCandidate'][3] for c in active)
        if bottom<=top or any(bottom-top < .8*(c['sourceTextCandidate'][3]-c['sourceTextCandidate'][1]) for c in active):continue
        candidates=[]
        spend(len(native_rows))
        for source,boxes,whole in native_rows:
            if not all(_inside(c['sourceTextCandidate'],whole) for c in active):continue
            if not _inside(whole,view) or any(_overlap(whole,b) for b in obstacles):continue
            matches=[]
            spend(len(source)*len(active))
            for c in active:
                found=[i for i,(n,b) in enumerate(zip(source,boxes)) if _inside(c['sourceTextCandidate'],b) and compact(n['text'])==compact(c['text'])]
                if len(found)!=1:break
                matches.append(found[0])
            if len(matches)!=len(active) or len(set(matches))!=len(matches):continue
            if set(matches)!={i for i,c in enumerate(source) if c['text'].strip()}:continue
            valid=True; all_glyphs=[]
            for c,index in zip(active,matches):
                spend(len(chars))
                b=boxes[index];glyphs=[g for g in chars if _overlap(_geometry(g),b)]
                if not glyphs or any(not _inside(_geometry(g),b) or not _inside(_geometry(g),view)
                    or not g.get('upright') or len(g.get('matrix',()))!=6
                    or not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in g['matrix'])
                    or g['matrix'][0]<=0 or g['matrix'][3]<=0 or abs(g['matrix'][1])>.001 or abs(g['matrix'][2])>.001
                    or not (c['sourceTextCandidate'][0]<=(g['x0']+g['x1'])/2<=c['sourceTextCandidate'][2]
                            and c['sourceTextCandidate'][1]<=(g['top']+g['bottom'])/2<=c['sourceTextCandidate'][3]) for g in glyphs):valid=False;break
                if compact(extract_text(glyphs,x_tolerance=2,y_tolerance=3))!=compact(c['text']):valid=False;break
                all_glyphs.extend(glyphs)
                spend(len(nonempty)*len(glyphs))
                if any(other is not c and any(other['sourceTextCandidate'][0]<=(g['x0']+g['x1'])/2<=other['sourceTextCandidate'][2]
                            and other['sourceTextCandidate'][1]<=(g['top']+g['bottom'])/2<=other['sourceTextCandidate'][3] for g in glyphs) for other in nonempty):valid=False;break
                spend(64*len(edges))
                if not all(closed_side(edges,h,pos,start,end) for h,pos,start,end in
                           [(True,b[1],b[0],b[2]),(True,b[3],b[0],b[2]),(False,b[0],b[1],b[3]),(False,b[2],b[1],b[3])]):valid=False;break
            if valid:
                spend(len(paint)*len(all_glyphs))
                if any(_overlap(_geometry(g),b) for g in all_glyphs for b in paint):continue
                if any(not black_glyph(g) or g['x1']-g['x0']<.5 for g in all_glyphs):continue
                ordered=sorted(all_glyphs,key=lambda g:g['x0'])
                if any(left['x1']-right['x0']>.05 for left,right in zip(ordered,ordered[1:])):continue
                baselines=[g['matrix'][5] for g in all_glyphs]
                if max(baselines)-min(baselines)>.5:continue
                if rendered is None:
                    w,h=math.ceil(page.width*2),math.ceil(page.height*2)
                    if w*h>20_000_000:return model
                    from source_row_visibility import contribution
                    proof=contribution(page)
                    if proof is None:return model
                    rendered,text_pixels=proof
                if (visible_glyphs(text_pixels,all_glyphs,page.width,page.height)
                        and all(visible_sides(rendered,b,page.width,page.height) for b in boxes)):
                    candidates.append(whole)
        if len(candidates)==1:joins.append(row)
    # Overlapping proposed joins indicate a three-row ambiguity, not a chain to guess.
    joins=[r for r in joins if r-1 not in joins and r+1 not in joins]
    if not joins:return model
    result=deepcopy(model)
    for row in reversed(joins):
        updated=[]
        for c in result['cells']:
            if c['r'] in (row,row+1) and not c['text'].strip():continue
            if c['r']==row+1:c['r']=row
            elif c['r']>row+1:c['r']-=1
            updated.append(c)
        result['cells']=updated
        result['heights'][row]+=result['heights'].pop(row+1)
    assert Counter(c['text'] for c in result['cells'] if c['text'].strip())==Counter(c['text'] for c in cells if c['text'].strip())
    return result


def visible_sides(image,box,width,height):
    """Final-render contrast, not merely native line objects or white paint."""
    sx,sy=image.shape[1]/width,image.shape[0]/height
    for horizontal,position,start,end in [(True,box[1],box[0],box[2]),(True,box[3],box[0],box[2]),(False,box[0],box[1],box[3]),(False,box[2],box[1],box[3])]:
        pixels=image if horizontal else image.T
        along=sx if horizontal else sy;across=sy if horizontal else sx
        first,last=math.ceil(start*along)+4,math.floor(end*along)-4
        if first<0 or last>pixels.shape[1] or last-first<6:return False
        center=round(position*across);proved=False
        for fixed in range(center-2,center+3):
            if fixed<4 or fixed+4>=pixels.shape[0]:continue
            ink=pixels[fixed,first:last].astype('int16')
            background=np.maximum(pixels[fixed-4,first:last],pixels[fixed+4,first:last]).astype('int16')
            if np.mean((ink<200)&(background-ink>=25))>=.95:proved=True;break
        if not proved:return False
    return True


def visible_glyphs(image,glyphs,width,height):
    sx,sy=image.shape[1]/width,image.shape[0]/height
    for glyph in glyphs:
        x0,y0,x1,y1=_geometry(glyph)
        x0,y0,x1,y1=math.floor(x0*sx),math.floor(y0*sy),math.ceil(x1*sx),math.ceil(y1*sy)
        if not 0<=x0<x1<=image.shape[1] or not 0<=y0<y1<=image.shape[0]:return False
        pixels=image[y0:y1,x0:x1]
        if np.count_nonzero(pixels)<2:return False
    return True


def black_glyph(glyph):
    color=glyph.get('non_stroking_color');space=glyph.get('ncs')
    if space=='DeviceGray':
        if isinstance(color,(tuple,list)) and len(color)==1:color=color[0]
        return _finite(color) and abs(color)<1e-6
    expected={'DeviceRGB':(0,0,0),'DeviceCMYK':(0,0,0,1)}.get(space)
    return (expected is not None and isinstance(color,(tuple,list)) and len(color)==len(expected)
            and all(_finite(v) and abs(v-e)<1e-6 for v,e in zip(color,expected)))
