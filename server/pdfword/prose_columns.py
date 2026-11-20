"""Recognize narrow newspaper gutters only with substantial prose on each side."""
import re


def narrow_prose_cuts(words,width,height):
    body=[w for w in words if height*.15<=w['top'] and w['bottom']<=height*.95]
    if len(body)<150:return []
    cuts=[]
    for target in (width/3,2*width/3):
        gaps=[];start=None
        for x in range(int(target-width*.08),int(target+width*.08)+1):
            occupied=any(w['x0']<x<w['x1'] for w in body)
            if not occupied and start is None:start=x
            if occupied and start is not None:
                if x-start>=6:gaps.append((x-start,(start+x-1)/2))
                start=None
        if not gaps:return []
        cuts.append(max(gaps)[1])
    if cuts[1]-cuts[0]<width*.2:return []
    for index in range(3):
        members=[w for w in body if sum(w['x0']>=c for c in cuts)==index
                 and not any(w['x0']<c<w['x1'] for c in cuts)]
        text=' '.join(w['text'] for w in members)
        if (len(text)<500 or len({round(w['top']/4) for w in members})<12
                or len(re.findall(r'[A-Za-z]{3,}[.!?](?:\s|$)',text))<2):
            return []
    return cuts


def native_font_families(page):
    """Choose a standard Word family from PDF font descriptors, not name guesses."""
    from pdfminer.pdftypes import resolve1
    from pdfminer.psparser import literal_name
    families={}
    try:
        fonts=resolve1(page.page_obj.resources.get('Font',{}))
        if len(fonts)>128:return {}
        for ref in fonts.values():
            font=resolve1(ref);descriptor=resolve1(font.get('FontDescriptor',{}))
            flags=int(descriptor.get('Flags',0));name=literal_name(font['BaseFont']).lower()
            if flags & 1:families[name]='Courier New'
            elif flags & 2 and not flags & 8:families[name]='Times New Roman'
    except (AttributeError,KeyError,TypeError,ValueError):
        return {}
    return families
