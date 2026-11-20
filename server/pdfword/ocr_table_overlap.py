"""Export one representation of spatially duplicated OCR table contents."""
import unicodedata
import re
from itertools import islice


def normalize(value):
    # Typography equivalence only. Digits, operators, casing and word boundaries
    # within the compact text are never corrected or inferred here.
    return ' '.join(unicodedata.normalize('NFKC',value).translate(
        str.maketrans({'’':"'",'‘':"'",'“':'"','”':'"'})).split())


def suppress_table_text_duplicates(blocks):
    if len(blocks)>2000:return blocks
    if sum(len(b.get("text", "")) + sum(len(c["text"]) for c in b.get("cells", [])) for b in blocks)>200000:
        return blocks
    removed=set()
    for table in (b for b in blocks if b['kind']=='table'):
        text=normalize(' '.join(c['text'] for c in table['cells']))
        if len(text)<40:continue
        left,top,right,bottom=table['bbox'];matches=[];conflict=False
        for index,block in enumerate(blocks):
            if index in removed or block['kind'] not in ('paragraph','list','heading'):continue
            value=normalize(block.get('text',''))
            if len(value)<(8 if block['kind']=='heading' else 12):continue
            l,t,r,b=block['bbox'];area=(r-l)*(b-t)
            overlap=max(0,min(r,right+4)-max(l,left-4))*max(0,min(b,bottom+4)-max(t,top-4))
            if area<=0 or overlap<.98*area:continue
            token = r"[A-Za-z0-9_+.-]"
            first = value[0].isascii() and (value[0].isalnum() or value[0] == '_')
            last = value[-1].isascii() and (value[-1].isalnum() or value[-1] == '_')
            pattern = (r"(?<!"+token+")" if first else "") + re.escape(value) + (r"(?!"+token+")" if last else "")
            positions=[m.start() for m in islice(re.finditer(pattern,text),2)]
            if len(positions)!=1:
                conflict=True
                continue
            start=positions[0]
            matches.append((index,start,start+len(value),block['bbox']))
        if not matches:continue
        if conflict:
            table['ocr_overlap_review']=True
            continue
        # A later physical paragraph must not precede an earlier table entry.
        if any(a[1]>b[1] and a[3][3]+2<b[3][1] for a in matches for b in matches):
            table['ocr_overlap_review']=True
            continue
        covered=0;end=0
        for _,start,stop,_ in sorted(matches,key=lambda m:m[1]):
            covered+=max(0,stop-max(start,end));end=max(end,stop)
        # Partial matching phrases are insufficient on their own. Require a
        # substantial shared representation, or one nearly complete duplicate.
        if covered<.3*len(text) or (len(matches)<2 and covered<.8*len(text)):
            # A detector may emit only the first-row labels twice. Their exact
            # cell identity and location at the table top provide stronger proof
            # than the fraction of total table text (often a very long panel).
            headers={normalize(c['text']) for c in table['cells'] if c.get('row')==0}
            matches=[m for m in matches if normalize(blocks[m[0]].get('text','')) in headers
                     and m[3][1]<=top+24 and m[3][3]<=top+32]
        if matches:
            removed.update(m[0] for m in matches)
            table['deduplicated_ocr_regions']=len(matches)
    return [b for i,b in enumerate(blocks) if i not in removed]
