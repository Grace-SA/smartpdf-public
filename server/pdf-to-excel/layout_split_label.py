"""Reunite one-line black label fragments in a proved closed source cell.

Never infer words or numbers. Only existing adjacent label strings are joined;
unsupported graphics and ambiguous glyph ownership leave the model unchanged.
"""
from copy import deepcopy
from itertools import accumulate
import math,re
from statistics import median
from pdfplumber.utils import extract_text
from layout_native_order import _box,_geometry,_inside,_overlap,_finite
from layout_nested_guard import closed_table
from layout_tables import visible_box,physical_page
from layout_body_rowspans import closed_side
from layout_split_rows import black_glyph,visible_sides,visible_glyphs
from source_row_visibility import contribution

_LABEL=re.compile(r'[A-Za-z][A-Za-z -]{0,199}\Z')

def recover(model,native,page):
    try:return _recover(model,native,page)
    except (ValueError,TypeError,KeyError,AttributeError,IndexError,OverflowError,OSError,RuntimeError):return model

def _recover(model,native,page):
    if (page.rotation or tuple(page.bbox)!=(0,0,page.width,page.height)
            or tuple(page.cropbox)!=tuple(page.mediabox)):return model
    rows,cols=len(model['heights']),len(model['widths']);cells=model['cells']
    if not 3<=rows<=300 or not 3<=cols<=30 or len(cells)>9000 or len(page.chars)>50000:return model
    if len(cells)*len(page.chars)>2_000_000 or len(native)>100:return model
    if any(not _finite(v) or v<=0 for v in model['heights']+model['widths']):return model
    used=set()
    for c in cells:
        if (not isinstance(c.get('text'),str) or any(type(c.get(k))is not int for k in ('r','c','rs','cs'))
                or not 0<=c['r']<c['r']+c['rs']<=rows or not 0<=c['c']<c['c']+c['cs']<=cols):return model
        slots={(r,col)for r in range(c['r'],c['r']+c['rs'])for col in range(c['c'],c['c']+c['cs'])}
        if slots&used:return model
        used.update(slots)
    nonempty=[c for c in cells if c['text'].strip()]
    if any(not _box(c.get('sourceTextCandidate'))for c in nonempty):return model
    tables=[t for t in native if closed_table(t)]
    if len(tables)!=1 or len(tables[0]['cells'])*len(cells)>500_000:return model
    t=tables[0];view=visible_box(page)
    if not _inside(t['bbox'],view):return model
    xs=list(accumulate(t['widths'],initial=t['bbox'][0]));ys=list(accumulate(t['heights'],initial=t['bbox'][1]))
    chars=[g for g in page.chars if g['text'].strip()]
    if any(not _box(_geometry(g))for g in chars):return model
    edges=physical_page(page).edges
    if len(edges)>10000 or len(page.edges)>10000 or len(page.curves)>10000:return model
    obstacles=[_geometry(o)for key in ('images','annots')for o in (getattr(page,key,[])or[])]
    obstacles += [_geometry(o)for o in page.rects+page.curves if o.get('fill')and o.get('width',0)>3 and o.get('height',0)>3]
    if any(not _box(b)for b in obstacles):return model
    paint=[]
    for e in page.edges+page.curves:
        width=e.get('linewidth',0)
        if not _finite(width)or not 0<=width<=100:return model
        pad=width*(10 if e.get('object_type')=='curve'else .5)+.5
        x0,y0,x1,y1=_geometry(e);paint.append((x0-pad,y0-pad,x1+pad,y1+pad))
    candidates=[c for c in cells if c['rs']==c['cs']==1 and _LABEL.fullmatch(c['text'])]
    by_slot={(c['r'],c['c']):c for c in candidates};proposals=[];proof=None;work=0
    def spend(n):
        nonlocal work
        work+=n
        if work>2_000_000:raise ValueError('Label recovery work budget')
    for left in candidates:
        right=by_slot.get((left['r'],left['c']+1))
        if right is None or not left['text'][-1].isalpha():continue
        a,b=left['sourceTextCandidate'],right['sourceTextCandidate']
        if not a[2]<b[0]:continue
        joined=left['text']+' '+right['text']
        matches=[];spend(len(t['cells']))
        for c in t['cells']:
            if c['rs']!=1 or c['cs']!=1 or c['text']!=joined:continue
            box=(xs[c['c']],ys[c['r']],xs[c['c']+1],ys[c['r']+1])
            if _inside(a,box)and _inside(b,box):matches.append(box)
        if len(matches)!=1:continue
        box=matches[0]
        if any(_overlap(box,o)for o in obstacles):continue
        spend(len(chars));glyphs=[g for g in chars if _overlap(_geometry(g),box)]
        if not glyphs or any(not _inside(_geometry(g),box)or not _inside(_geometry(g),view)
                or not isinstance(g.get('fontname'),str)or not g['fontname']
                or not g.get('upright')or len(g.get('matrix',()))!=6
                or any(not _finite(v)for v in g['matrix'])or g['matrix'][0]<=0 or g['matrix'][3]<=0
                or abs(g['matrix'][1])>.001 or abs(g['matrix'][2])>.001
                or not black_glyph(g)or g['x1']-g['x0']<.5 for g in glyphs):continue
        if (max(g['matrix'][5]for g in glyphs)-min(g['matrix'][5]for g in glyphs)>.5
                or len({g.get('fontname')for g in glyphs})!=1
                or max(g['bottom']-g['top']for g in glyphs)-min(g['bottom']-g['top']for g in glyphs)>.1):continue
        ordered=sorted(glyphs,key=lambda g:g['x0'])
        if any(x['x1']-y['x0']>.05 for x,y in zip(ordered,ordered[1:])):continue
        groups=[]
        for cell,bounds in ((left,a),(right,b)):
            group=[g for g in glyphs if bounds[0]<=(g['x0']+g['x1'])/2<=bounds[2]and bounds[1]<=(g['top']+g['bottom'])/2<=bounds[3]]
            if not group or ''.join(extract_text(group).split())!=''.join(cell['text'].split()):break
            groups.append(group)
        if len(groups)!=2 or set(map(id,groups[0]))&set(map(id,groups[1]))or set(map(id,groups[0]+groups[1]))!=set(map(id,glyphs)):continue
        gap=min(g['x0']for g in groups[1])-max(g['x1']for g in groups[0])
        if not .5<=gap<=median(g['bottom']-g['top']for g in glyphs)*.65:continue
        end=max(groups[0],key=lambda g:g['x1']);start=min(groups[1],key=lambda g:g['x0'])
        spend(len(page.chars))
        spaces=[g for g in page.chars if g.get('text')==' ' and _box(_geometry(g))
                and end['x1']<=(g['x0']+g['x1'])/2<=start['x0']
                and abs(g['top']-end['top'])<=.1 and abs(g['bottom']-end['bottom'])<=.1]
        if (len(spaces)!=1 or end.get('fontname')!=start.get('fontname')
                or spaces[0].get('fontname')!=end.get('fontname')
                or abs(spaces[0]['x0']-end['x1'])>.1 or abs(spaces[0]['x1']-start['x0'])>.1
                or not _inside(_geometry(spaces[0]),box)):continue
        spend(len(nonempty)*len(glyphs))
        if any(c is not left and c is not right and any(c['sourceTextCandidate'][0]<=(g['x0']+g['x1'])/2<=c['sourceTextCandidate'][2]and c['sourceTextCandidate'][1]<=(g['top']+g['bottom'])/2<=c['sourceTextCandidate'][3]for g in glyphs)for c in nonempty):continue
        if extract_text(glyphs,x_tolerance=2,y_tolerance=3)!=joined:continue
        spend(len(paint)*len(glyphs))
        if any(_overlap(_geometry(g),p)for g in glyphs for p in paint):continue
        spend(64*len(edges))
        if not all(closed_side(edges,h,pos,start,end)for h,pos,start,end in [(True,box[1],box[0],box[2]),(True,box[3],box[0],box[2]),(False,box[0],box[1],box[3]),(False,box[2],box[1],box[3])]):continue
        if proof is None:
            proof=contribution(page)
            if proof is None:return model
        image,mask=proof
        if visible_sides(image,box,page.width,page.height)and visible_glyphs(mask,glyphs,page.width,page.height):proposals.append((left,right))
    # A fragment participating in two joins is ambiguous, not a chain to guess.
    counts={id(c):sum(c is a or c is b for a,b in proposals)for pair in proposals for c in pair}
    proposals=[(a,b)for a,b in proposals if counts[id(a)]==counts[id(b)]==1]
    if not proposals:return model
    out=deepcopy(model);removed=set()
    for a,b in proposals:
        ia=next(i for i,c in enumerate(cells)if c is a);ib=next(i for i,c in enumerate(cells)if c is b)
        c=out['cells'][ia];c['text']=a['text']+' '+b['text'];c['cs']=2
        c['sourceTextCandidate']=[min(a['sourceTextCandidate'][i],b['sourceTextCandidate'][i])if i<2 else max(a['sourceTextCandidate'][i],b['sourceTextCandidate'][i])for i in range(4)]
        for key in ('sourceTextBox','sourceFont','glyphWidths'):c.pop(key,None)
        removed.add(ib)
    out['cells']=[c for i,c in enumerate(out['cells'])if i not in removed]
    return out
