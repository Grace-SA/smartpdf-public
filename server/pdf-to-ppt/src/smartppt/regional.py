"""Recover editable native objects without sacrificing the rest of a page.

Every accepted object has complete PDF character provenance and is checked against
an independent office render. Unaccepted objects stay in the source background.
This is partial editability, never a claim that all PDF text was reconstructed.
"""
from collections import defaultdict
from contextlib import closing
from copy import deepcopy
import ctypes
import math
import shutil
from pathlib import Path
import tempfile
import unicodedata
import numpy as np
import pypdfium2 as pdfium
from pptx import Presentation
from pptx.util import Pt
from .layout import extract_native, merge_native_runs, page_background, add_background, add_text
from .pdf import render_page
from .render_gate import render_presentations


def aligned_source(page, size):
    w,h=page.get_size()
    # Render directly on the comparison grid. Resizing an already rasterized
    # page changes thin glyph edges and can create a one-pixel false regression.
    scale=min(size[0]/w,size[1]/h)
    width,height=round(w*scale),round(h*scale)
    with closing(pdfium.PdfBitmap.new_native(*size,format=pdfium.raw.FPDFBitmap_BGR)) as bitmap:
        bitmap.fill_rect((255,255,255,255),0,0,*size)
        pdfium.raw.FPDF_RenderPageBitmap(bitmap,page,(size[0]-width)//2,(size[1]-height)//2,width,height,0,pdfium.raw.FPDF_ANNOT)
        return bitmap.to_pil().convert('RGB').copy()


def pixel_score(a,b):
    av,bv=np.asarray(a,dtype=float),np.asarray(b,dtype=float)
    mask=(av.min(axis=2)<235)|(bv.min(axis=2)<235)
    return {'mae':float(np.abs(av-bv).mean()/255),
            'foreground_mae':float(np.abs(av-bv)[mask].mean()/255) if mask.any() else 0}


def acceptable_region(score):
    return score['mae']<=.035 and score['foreground_mae']<=.16


def acceptable_page(baseline, candidate):
    # Rasterizing an unchanged page through Office itself changes antialiasing.
    # Keep the absolute floor, then require no material regression over that
    # identical-renderer image baseline. Each edited run has a separate gate.
    return (candidate['mae']<=max(.006,baseline['mae']+.001) and
            candidate['foreground_mae']<=max(.12,baseline['foreground_mae']+.01))


def score_regions(expected, actual, boxes, prs):
    """Every run must pass; a large object must not dilute a missing short line."""
    scores=[]
    for box in boxes:
        bounds=region_box(box,actual.size,prs)
        if bounds is None:return None
        a,b=expected.crop(bounds),actual.crop(bounds)
        av,bv=np.asarray(a,dtype=float),np.asarray(b,dtype=float)
        border=np.concatenate((av[0],av[-1],av[:,0],av[:,-1]))
        background=np.median(border,axis=0)
        # Complex backgrounds remain raster. Foreground is measured relative to
        # the actual paper color, so dark/tinted regions cannot hide lost glyphs.
        if np.quantile(np.abs(border-background),.95)>12:return None
        ink=(np.max(np.abs(av-background),axis=2)>20)|(np.max(np.abs(bv-background),axis=2)>20)
        if not ink.any():return None
        score={'mae':float(np.abs(av-bv).mean()/255),'foreground_mae':float(np.abs(av-bv)[ink].mean()/255)}
        if not acceptable_region(score):return None
        scores.append(score)
    return scores or None


def objects_for_page(page,grouped=True):
    runs,objects,warnings=extract_native(page);groups=defaultdict(list)
    for run in runs:groups[run['object_id']].append(run)
    safe=[]
    for obj in objects:
        pointer=ctypes.cast(obj.raw,ctypes.c_void_p).value
        parts=groups[pointer]
        # Fill-only opaque text; clipping, strokes, transparency and replacement
        # glyphs cannot be represented faithfully by an ordinary PPT textbox.
        rgba=[ctypes.c_uint() for _ in range(4)]
        if (pdfium.raw.FPDFTextObj_GetTextRenderMode(obj)!=0 or
            any(name in obj.get_font().get_base_name().lower() for name in ('wingdings','zapfdingbats','symbol')) or
            not pdfium.raw.FPDFPageObj_GetFillColor(obj,*rgba) or rgba[3].value!=255 or
            any('\ufffd' in r['text'] or any(0xD800<=ord(c)<=0xDFFF for c in r['text']) for r in parts)):
            continue
        if parts:safe.append((obj,parts))
    if not grouped:return [([obj],parts) for obj,parts in safe],warnings
    # A single glyph per PDF object is common in browser-generated reports.
    # Verify a complete line as one candidate, while retaining every underlying
    # object in its atomic removal set. Never split a multi-line source object.
    by_id={ctypes.cast(obj.raw,ctypes.c_void_p).value:obj for obj,parts in safe}
    singles=sorted((parts[0] for obj,parts in safe if len(parts)==1),key=lambda r:r['index'])
    grouped=[([by_id[p] for p in dict.fromkeys(run['object_ids'])],[run]) for run in merge_native_runs(page,singles)]
    grouped.extend(([obj],parts) for obj,parts in safe if len(parts)!=1)
    grouped.sort(key=lambda item:min(r['index'] for r in item[1]))
    return grouped,warnings


def draw_objects(prs,slide,page,objects):
    for shape in list(slide.shapes):shape._element.getparent().remove(shape._element)
    w,h=page.get_size();sw,sh=prs.slide_width/12700,prs.slide_height/12700
    scale=min(sw/w,sh/h);ox=(sw-w*scale)/2;oy=(sh-h*scale)/2
    add_background(slide,page_background(page,[obj for group,_ in objects for obj in group]),w*scale,h*scale,(ox,oy))
    regions=[]
    for _,runs in objects:
        boxes=[]
        for run in runs:
            l,b,r,t=run['box'];fs=run['size']
            shape=add_text(slide,run['text'],ox+l*scale,oy+(h-t-fs*.18)*scale,
                (r-l+fs*.3)*scale,fs*1.5*scale,fs*scale,run['font'],run['bold'],run['color'],italic=run['italic'])
            if 'fit' in run:
                fit=run['fit'];shape.left=Pt(fit['x']);shape.top=Pt(fit['y'])
                shape.width=Pt(fit['width']);shape.height=Pt(fit['height'])
                text_run=shape.text_frame.paragraphs[0].runs[0];text_run.font.size=Pt(fit['size'])
                text_run._r.get_or_add_rPr().set('spc',str(fit['spacing']))
            # Include both the original ink and the complete new text box.
            boxes.append((min(ox+l*scale,shape.left/12700), min(oy+(h-t)*scale,shape.top/12700),
                          max(ox+r*scale,(shape.left+shape.width)/12700),
                          max(oy+(h-b)*scale,(shape.top+shape.height)/12700)))
        regions.append(boxes)
    return regions


def region_box(box, size, prs):
    sx,sy=size[0]/(prs.slide_width/12700),size[1]/(prs.slide_height/12700)
    l,t,r,b=box
    # Entire region must be on the canvas; clipping is not a successful recovery.
    if not all(math.isfinite(v) for v in box) or l<0 or t<0 or r<=l or b<=t or r*sx>size[0] or b*sy>size[1]:return None
    return max(0,math.floor(l*sx)-2),max(0,math.floor(t*sy)-2),min(size[0],math.ceil(r*sx)+2),min(size[1],math.ceil(b*sy)+2)


def calibrate_runs(prs, number, page, objects, rendered):
    """Measure the office renderer's glyph placement, then fit source ink bounds.

    Numeric/character content is never edited. Ambiguous or implausible matches
    remain uncalibrated and must still pass the independent pixel gate.
    """
    w,h=page.get_size();sw,sh=prs.slide_width/12700,prs.slide_height/12700
    scale=min(sw/w,sh/h);ox=(sw-w*scale)/2;oy=(sh-h*scale)/2
    with pdfium.PdfDocument(rendered) as doc,closing(doc[number-1]) as actual,closing(actual.get_textpage()) as tp:
        chars=[];boxes=[]
        for i in range(tp.count_chars()):
            code=pdfium.raw.FPDFText_GetUnicode(tp,i)
            if not code:continue
            value=unicodedata.normalize('NFKC',chr(code))
            for c in value:
                if not c.isspace():chars.append(c);boxes.append(tp.get_charbox(i))
        text=''.join(chars);used=set()
        shapes=iter(s for s in prs.slides[number-1].shapes if s.has_text_frame)
        for _,runs in objects:
            for run in runs:
                shape=next(shapes)
                needle=''.join(unicodedata.normalize('NFKC',run['text']).split())
                if not needle:continue
                l,b,r,t=run['box'];desired=(ox+l*scale,oy+(h-t)*scale,ox+r*scale,oy+(h-b)*scale)
                matches=[];start=0
                while (start:=text.find(needle,start))>=0:
                    end=start+len(needle)
                    if not used.intersection(range(start,end)):
                        bs=boxes[start:end]
                        observed=(min(x[0] for x in bs),sh-max(x[3] for x in bs),max(x[2] for x in bs),sh-min(x[1] for x in bs))
                        distance=abs(desired[0]-observed[0])+abs(desired[1]-observed[1])
                        matches.append((distance,start,end,observed))
                    start+=1
                if not matches:continue
                distance,start,end,observed=min(matches)
                if distance>max(12,run['size']*2):continue
                used.update(range(start,end))
                aw,ah=observed[2]-observed[0],observed[3]-observed[1]
                dw,dh=desired[2]-desired[0],desired[3]-desired[1]
                if min(aw,ah,dw,dh)<=0:continue
                ratio=dh/ah
                if not .8<=ratio<=1.2 or not .7<=dw/(aw*ratio)<=1.3:continue
                count=len(run['text'])
                spacing=(dw-aw*ratio)/max(1,count-1)
                size=shape.text_frame.paragraphs[0].runs[0].font.size/12700*ratio
                if abs(spacing)>size*.2:continue
                run['fit']={'x':desired[0]-(observed[0]-shape.left/12700)*ratio,
                    'y':desired[1]-(observed[1]-shape.top/12700)*ratio,
                    'width':dw+size,'height':size*1.8,'size':size,'spacing':round(spacing*100)}


def _recover_regions(source, target, page_numbers, settings,grouped=False):
    """Mutate only verified pages. Renderer errors leave the caller's fallback intact."""
    if not page_numbers:return {}
    reports={}
    with tempfile.TemporaryDirectory(prefix='smartppt-regions-',dir=Path(source).parent) as tmp,pdfium.PdfDocument(source) as doc:
        folder=Path(tmp);prs=Presentation(target);pages={};candidates={};regions={}
        # Keep page handles alive: PDF object identities must not cross a reopen.
        try:
            for number in page_numbers:
                page=pages[number]=doc[number-1]
                objects,warnings=objects_for_page(page,grouped=grouped)
                if objects:
                    candidates[number]=objects
                    regions[number]=draw_objects(prs,prs.slides[number-1],page,objects)
            if not candidates:return {}
            candidate=folder/'candidate.pptx';prs.save(candidate)
            baseline=folder/'baseline.pptx';shutil.copyfile(target,baseline)
            baseline_pdf,rendered=render_presentations([baseline,candidate],folder,settings)
            for number,objects in candidates.items():
                calibrate_runs(prs,number,pages[number],objects,rendered)
                regions[number]=draw_objects(prs,prs.slides[number-1],pages[number],objects)
            calibrated=folder/'calibrated.pptx';prs.save(calibrated)
            rendered=render_presentations([calibrated],folder,settings)[0]
            selected={};scores={}
            for number,objects in candidates.items():
                actual=render_page(rendered,number-1,max_side=1800)
                expected=aligned_source(pages[number],actual.size)
                chosen=[];measurements=[]
                for obj,boxes in zip(objects,regions[number]):
                    measured=score_regions(expected,actual,boxes,prs)
                    if measured:chosen.append(obj);measurements.extend(measured)
                if chosen:selected[number]=chosen;scores[number]=measurements
            if not selected:return {}
            # Rebuild from the pre-recovery package: failed pages must not inherit
            # any unverified candidate shapes or newly referenced images.
            final=Presentation(target);fallback=Presentation(target)
            for number,objects in selected.items():
                draw_objects(final,final.slides[number-1],pages[number],objects)
            verified=folder/'verified.pptx';final.save(verified)
            final_pdf=render_presentations([verified],folder,settings)[0]
            # A second whole-page check catches interactions between text objects,
            # clipping, shared resources and pixels outside their measured boxes.
            for number,objects in selected.items():
                actual=render_page(final_pdf,number-1,max_side=1800)
                expected=aligned_source(pages[number],actual.size)
                score=pixel_score(expected,actual)
                baseline_score=pixel_score(expected,render_page(baseline_pdf,number-1,max_side=1800))
                if not acceptable_page(baseline_score,score):
                    slide=final.slides[number-1]
                    for shape in list(slide.shapes):shape._element.getparent().remove(shape._element)
                    for shape in fallback.slides[number-1].shapes:
                        slide.shapes._spTree.insert_element_before(deepcopy(shape._element),'p:extLst')
                    continue
                runs=[run for _,parts in objects for run in parts]
                reports[number]={'route':'native-regions','editable_runs':len(runs),'editable_objects':sum(len(group) for group,_ in objects),
                    'candidate_objects':sum(len(group) for group,_ in candidates[number]),'candidate_regions':len(candidates[number]),'source_text_characters':sum(len(r['text']) for r in runs),
                    'regional_strategy':'joined-glyphs' if grouped else 'source-objects',
                    'font_substitutions':sorted({r['source_font']+' → '+r['font'] for r in runs if r['substituted']}),
                    'region_scores':scores[number],'final_render':score,'baseline_render':baseline_score,
                    'warnings':['partial_native_editability','unrecovered_content_kept_as_graphic'],
                    'graphics':'raster; not editable'}
            if reports:final.save(target)
        finally:
            for page in pages.values():page.close()
    return reports


def recover_regions(source,target,page_numbers,settings):
    """Keep verified object recovery; try joined glyphs only on remaining pages."""
    from .config import ConversionError
    reports=_recover_regions(source,target,page_numbers,settings,grouped=False)
    remaining=[n for n in page_numbers if n not in reports]
    if remaining:
        try:reports.update(_recover_regions(source,target,remaining,settings,grouped=True))
        except ConversionError:
            if not reports:raise
            # The first pass already saved verified shapes. Do not discard its
            # metadata or claim those pages are still whole-page images.
            for report in reports.values():report['warnings'].append('additional_grouped_recovery_unavailable')
    return reports
