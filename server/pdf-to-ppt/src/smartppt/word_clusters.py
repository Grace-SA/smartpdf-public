"""Bounded atomic words whose padded removal boxes collide.

Do not relax per-word geometry/pixel gates or split a rejected component.
"""
import math


def intersects(a,b):
    return a[0]<b[2] and b[0]<a[2] and a[1]<b[3] and b[1]<a[3]


MAX_PAGE_RUNS=3000
MAX_SOURCE_CHARS=100000
MAX_NEIGHBOR_LINKS=100000


def bounded_neighbors(memberships,cells,max_links=MAX_NEIGHBOR_LINKS):
    """Bound retained adjacency before allocating the complete page graph."""
    result=[];links=0
    for keys in memberships:
        nearby=set()
        for key in keys:
            nearby.update(cells[key])
            if links+len(nearby)>max_links:return None
        links+=len(nearby);result.append(nearby)
    return result


def connected_word_clusters(parts,boxes,neighbors,blocked_pixels,mode='adjacent'):
    if mode not in ('adjacent','collision'):raise ValueError('unknown word cluster mode')
    selected=[];seen=set()
    for first in range(len(parts)):
        if first in seen:continue
        pending=[first];component=set()
        while pending:
            i=pending.pop()
            if i in component:continue
            component.add(i);seen.add(i)
            pending.extend(j for j in neighbors[i] if j not in component and intersects(boxes[i],boxes[j]))
        if not 2<=len(component)<=8:continue
        ordered=sorted(component,key=lambda i:parts[i][1]['index'])
        runs=[parts[i][1] for i in ordered]
        if any(intersects(boxes[i],b) for i in component for b in blocked_pixels):continue
        if sum(len(r['text']) for r in runs)>=160:continue
        if any(r.get('rotation') or r.get('baseline') is None for r in runs):continue
        keys=('font','source_font','source_base_font','bold','italic','color','size')
        if any(any(r[k]!=runs[0][k] for k in keys) for r in runs):continue
        if any(not all(math.isfinite(v) for v in (*r['box'],r['baseline'])) for r in runs):continue
        if mode=='adjacent' and max(r['baseline'] for r in runs)-min(r['baseline'] for r in runs)>.1:continue
        if max(r['box'][2] for r in runs)-min(r['box'][0] for r in runs)>200:continue
        if mode=='adjacent':
            if any(a['end_index']!=b['index'] or not a['text'].endswith(' ') or
                   b['box'][0]<a['box'][2] for a,b in zip(runs,runs[1:])):continue
        else:
            # Runs remain separate, never joined across omitted source text.
            # Full collision components can span nearby lines, but neither
            # source ranges nor actual ink boxes may overlap.
            if max(r['box'][3] for r in runs)-min(r['box'][1] for r in runs)>50:continue
            if any(a['end_index']>b['index'] for a,b in zip(runs,runs[1:])):continue
            if any(intersects(a['box'],b['box']) for i,a in enumerate(runs) for b in runs[i+1:]):continue
        objects=[]
        for i in ordered:
            obj=parts[i][0]
            if not any(obj is other for other in objects):objects.append(obj)
        selected.append((objects,[dict(r,source_region=True,word_cluster=True) for r in runs]))
    selected.sort(key=lambda item:item[1][0]['index'])
    return selected


def source_verified(page,runs):
    """Exact character ranges and owners, including the literal interword spaces."""
    import ctypes
    from contextlib import closing
    import pypdfium2 as pdfium
    with closing(page.get_textpage()) as tp:
        for run in runs:
            start,end=run['index'],run['end_index']
            if not 0<=start<end<=tp.count_chars():return False
            text=[]
            for i in range(start,end):
                if pdfium.raw.FPDFText_IsGenerated(tp,i)!=0:return False
                code=pdfium.raw.FPDFText_GetUnicode(tp,i)
                if not code or code in (0xfffd,0xfffe,0xffff):return False
                text.append(chr(code));obj=tp.get_textobj(i)
                # Every literal character needs its exact owner. Generated
                # separators were excluded even if PDFium assigned an owner.
                if obj is None or ctypes.cast(obj.raw,ctypes.c_void_p).value!=run['object_id']:return False
            if ''.join(text)!=run['text']:return False
    return True


def trim_generated_tails(page,runs):
    """Copy runs, optionally removing one inferred terminal ASCII separator.

    Only collision candidates may use this normalization. It does not authorize
    a run: callers must still call source_verified on the result, retain the
    original collision graph/geometry, and keep every word as a separate shape.
    Real spaces, multiple trailing spaces, internal generated characters and
    malformed/expanded Unicode ranges are never normalized.
    """
    from contextlib import closing
    import pypdfium2 as pdfium
    from copy import deepcopy
    copied=[deepcopy(run) for run in runs]
    with closing(page.get_textpage()) as tp:
        count=tp.count_chars()
        for run in copied:
            text=run.get('text');start=run.get('index');end=run.get('end_index')
            if (not isinstance(text,str) or len(text)<2 or not text.endswith(' ')
                    or text[-2].isspace() or type(start) is not int or type(end) is not int
                    or not 0<=start<end<=count or end-start!=len(text)):
                continue
            if pdfium.raw.FPDFText_IsGenerated(tp,end-1)!=1:continue
            # The full original span must be exactly this string, not a guessed
            # separator from NFKC, a truncated range, or a generated glyph.
            if any(pdfium.raw.FPDFText_GetUnicode(tp,i)!=ord(char)
                   for i,char in enumerate(text,start)):continue
            if any(pdfium.raw.FPDFText_IsGenerated(tp,i)!=0 for i in range(start,end-1)):continue
            run['text']=text[:-1];run['end_index']=end-1
            run['generated_tail_space_trimmed']=True
            run['source_original_end_index']=end
    return copied
