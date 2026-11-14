"""Conservative refusal of reordered multi-record text inside one model cell.

Whole text-show identity and rendered contribution support a structural conflict;
this does not certify all glyph shapes or authorize text reconstruction.
"""
import math,re
from pypdf.errors import PyPdfError
from pdfminer.pdfexceptions import PDFException
from pdfminer.psexceptions import PSException
from pdfplumber.utils.exceptions import MalformedPDFException
from layout_tables import LayoutError
from layout_native_order import _box,_finite,_overlap
from source_record_evidence import Evidence

NOTICE=('Several separately positioned source records appear reordered inside one spreadsheet cell. '
        'Their associations could not be verified; conversion was stopped rather than exporting mixed records.')
def compact(s):return ''.join(s.split())
def verify(model,page):
    try:
        stream=page.pdf.stream;position=stream.tell()
    except (AttributeError,OSError,ValueError):return
    try:
        try:bad=_conflict(model,page)
        except (ValueError,TypeError,KeyError,AttributeError,IndexError,OverflowError,OSError,RuntimeError,PyPdfError,MalformedPDFException,PDFException,PSException):return
    finally:
        stream.seek(position)
    if bad:raise LayoutError(NOTICE)

def _conflict(model,page):
    if page.rotation or tuple(page.bbox)!=(0,0,page.width,page.height)or tuple(page.cropbox)!=tuple(page.mediabox):return False
    if len(page.images)or len(page.annots)or len(page.chars)>10000 or len(page.edges)>2000:return False
    if not _finite(page.width)or not _finite(page.height)or min(page.width,page.height)<=0 or math.ceil(page.width*2)*math.ceil(page.height*2)>3_000_000:return False
    if not model.get('method','').startswith('layout'):return False
    cells=model['cells'];rows=len(model['heights']);cols=len(model['widths'])
    if cols!=2 or not 5<=rows<=60 or not 5<=len(cells)<=120:return False
    if any(not isinstance(c.get('text'),str)or len(c['text'])>3000 or any(type(c.get(k))is not int for k in('r','c','rs','cs'))for c in cells):return False
    if any(not 0<=c['r']<c['r']+c['rs']<=rows or not 0<=c['c']<c['c']+c['cs']<=cols for c in cells):return False
    # Do not turn ordinary paragraph wrapping or duplicates into conflicts.
    candidates=[c for c in cells if c['c']==0 and c['rs']==c['cs']==1 and 160<=len(c['text'])<=1800 and _box(c.get('sourceTextCandidate'))]
    if not candidates or len(candidates)>2:return False
    nonempty=[c for c in cells if c['text'].strip()]
    cell_text={id(c):compact(c['text'])for c in nonempty}
    box_owners=[c for c in cells if _box(c.get('sourceTextCandidate'))]
    evidence=Evidence(page);records=[];work=0
    all_glyphs=[g for s in evidence.shows for g in s['glyphs']if g['text'].strip()]
    for index,show in enumerate(evidence.shows):
        glyphs=[g for g in show['glyphs']if g['text'].strip()]
        if not 12<=len(glyphs)<=220:continue
        if any(not _box(g['bbox'])or len(g['matrix'])!=6 or not all(_finite(v)for v in g['matrix'])or abs(g['matrix'][1])>.001 or abs(g['matrix'][2])>.001 or g['matrix'][0]<=0 or g['matrix'][3]<=0 or not 6<=g['bbox'][3]-g['bbox'][1]<=18 for g in glyphs):continue
        if max(g['bbox'][1]for g in glyphs)-min(g['bbox'][1]for g in glyphs)>.1:continue
        ordered=sorted(glyphs,key=lambda g:g['bbox'][0])
        if ordered!=glyphs or any(b['bbox'][0]-a['bbox'][0]<.5 or a['bbox'][2]-b['bbox'][0]>min(a['bbox'][3]-a['bbox'][1],b['bbox'][3]-b['bbox'][1])*.1 for a,b in zip(ordered,ordered[1:])):continue
        gaps=[i+1 for i,(a,b)in enumerate(zip(ordered,ordered[1:]))if b['bbox'][0]-a['bbox'][2]>24]
        if len(gaps)!=1:continue
        left,right=ordered[:gaps[0]],ordered[gaps[0]:]
        lt=compact(''.join(g['text']for g in left));rt=compact(''.join(g['text']for g in right))
        if not 6<=len(lt)<=70 or not 12<=len(rt)<=150 or not any(c.isalpha()for c in lt):continue
        if not any(lt in compact(c['text'])for c in candidates):continue
        # No source glyph belonging to another show may overlap these glyph boxes.
        ids={id(g)for g in glyphs}
        others=[g for g in all_glyphs if id(g)not in ids]
        work+=len(others)*len(glyphs)
        if work>2_000_000:return False
        if any(_overlap(g['bbox'],h['bbox'])for g in glyphs for h in others):continue
        records.append(dict(show=index,left=lt,right=rt,x0=left[0]['bbox'][0],x1=right[-1]['bbox'][2],top=page.height-max(g['bbox'][3]for g in glyphs),bottom=page.height-min(g['bbox'][1]for g in glyphs),leftGlyphs=left,rightGlyphs=right))
    # Corroborate whole right-side strings with one geometry owner. Partial
    # ownership or a repeated string without enough distinct output occurrences
    # cannot be borrowed as evidence for multiple source records.
    from collections import Counter
    ownership=[]
    for r in records:
        owner=None;good=True
        work+=len(r['rightGlyphs'])*len(box_owners)
        if work>2_000_000:return False
        for g in r['rightGlyphs']:
            x=(g['bbox'][0]+g['bbox'][2])/2;y=page.height-(g['bbox'][1]+g['bbox'][3])/2
            choices=[c for c in box_owners if c['sourceTextCandidate'][0]<=x<=c['sourceTextCandidate'][2]and c['sourceTextCandidate'][1]<=y<=c['sourceTextCandidate'][3]]
            if len(choices)!=1 or choices[0]['c']!=1 or choices[0]['cs']!=1 or(owner is not None and choices[0]is not owner):good=False;break
            owner=choices[0]
        if good and owner is not None and id(owner)in cell_text and r['right']in cell_text[id(owner)]:ownership.append((r,owner))
    counts=Counter((id(c),r['right'])for r,c in ownership)
    records=[r for r,c in ownership if cell_text[id(c)].count(r['right'])==counts[id(c),r['right']]]
    for candidate in candidates:
        text=compact(candidate['text']);box=candidate['sourceTextCandidate'];matches=[]
        for r in records:
            work+=len(r['leftGlyphs'])*len(box_owners)+len(nonempty)
            if work>2_000_000:return False
            if text.count(r['left'])!=1:continue
            unique=True
            for g in r['leftGlyphs']:
                x=(g['bbox'][0]+g['bbox'][2])/2;y=page.height-(g['bbox'][1]+g['bbox'][3])/2
                choices=[c for c in box_owners if c['sourceTextCandidate'][0]<=x<=c['sourceTextCandidate'][2]and c['sourceTextCandidate'][1]<=y<=c['sourceTextCandidate'][3]]
                if len(choices)!=1 or choices[0]is not candidate:unique=False;break
            if not unique:continue
            owners=[c for c in nonempty if cell_text[id(c)].count(r['left'])]
            if len(owners)!=1 or owners[0]is not candidate:continue
            matches.append(r)
        matches.sort(key=lambda r:r['top'])
        if not 4<=len(matches)<=6 or sum(any(ch.isdigit()for ch in r['right'])for r in matches)<3 or len({r['left']for r in matches})!=len(matches)or len({r['right']for r in matches})<3:continue
        if max(r['x0']for r in matches)-min(r['x0']for r in matches)>1 or max(r['x1']for r in matches)-min(r['x1']for r in matches)>3:continue
        if any(not 1<=b['top']-a['bottom']<=15 for a,b in zip(matches,matches[1:])):continue
        intervals=[(text.index(r['left']),text.index(r['left'])+len(r['left']))for r in matches]
        if any(max(a[0],b[0])<min(a[1],b[1])for i,a in enumerate(intervals)for b in intervals[i+1:]):continue
        if all(a[0]<b[0]for a,b in zip(intervals,intervals[1:])):continue
        if all(evidence.visible(r['show'])for r in matches):return True
    return False
