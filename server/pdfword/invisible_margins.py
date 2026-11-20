"""Exclude proven invisible white printer marks from native text extraction."""
import ctypes
import math
from itertools import islice
import pypdfium2 as pdf
from contextlib import closing
from text_geometry import handle
from text_visibility import confirm_invisible_numbers


def proven_margin_objects(page, textpage):
    if page.get_rotation():
        return []
    objects=list(islice(page.get_objects(max_depth=8),10001))
    # Mixed image pages retain their established OCR route; do not turn a scan
    # with a digital page label into an image-only Word page.
    if len(objects)>10000 or any(o.type==pdf.raw.FPDF_PAGEOBJ_IMAGE for o in objects):
        return []
    width,height=page.get_size()
    if any(abs(a-b)>.01 for a,b in zip(page.get_bbox(),(0,0,width,height))):
        return []
    result=[]
    for obj in page.get_objects(max_depth=1,textpage=textpage):
        if obj.type!=pdf.raw.FPDF_PAGEOBJ_TEXT:
            continue
        rgba=[ctypes.c_uint() for _ in range(4)]
        if (not pdf.raw.FPDFPageObj_GetFillColor(obj,*(ctypes.byref(v) for v in rgba))
                or [v.value for v in rgba]!=[255,255,255,255]
                or pdf.raw.FPDFTextObj_GetTextRenderMode(obj)!=0):
            continue
        left,bottom,right,top=obj.get_bounds()
        if not all(math.isfinite(v) for v in (left,bottom,right,top)):
            return []
        # Off-page objects are not printer marks in the visible margin. Their
        # character boxes can be clipped differently by the two PDF readers;
        # trying to map them would disable otherwise verified native OCR text.
        if right <= 0 or left >= width or top <= 0 or bottom >= height:
            continue
        if right<=36 or left>=width-36 or top<=36 or bottom>=height-36:
            result.append(obj)
            if len(result)>32:return []
    # Toggles drawing modes only in memory and restores them in finally; no PDF
    # content regeneration, float rounding, or source-file mutation is involved.
    return result if confirm_invisible_numbers(page,result) else []


def exclude_margin_text(page,native):
    with closing(page.get_textpage()) as textpage:
        objects=proven_margin_objects(page,textpage)
        if not objects:return native
        owners={handle(obj) for obj in objects};removed=set()
        for index in range(textpage.count_chars()):
            if handle(pdf.raw.FPDFText_GetTextObject(textpage,index)) not in owners:
                continue
            code=pdf.raw.FPDFText_GetUnicode(textpage,index)
            if not code or chr(code).isspace():continue
            l,b,r,t=textpage.get_charbox(index)
            matches=[i for i,c in enumerate(native.chars) if c['text']==chr(code)
                     and c['x0']-.5<=l<=r<=c['x1']+.5
                     and c['top']-.5<=native.height-t<=native.height-b<=c['bottom']+.5]
            if len(matches)!=1 or matches[0] in removed:return None
            removed.add(matches[0])
    view=native.filter(lambda _:True);view._objects=dict(native.objects)
    view._objects['char']=[c for i,c in enumerate(native.chars) if i not in removed]
    return view
