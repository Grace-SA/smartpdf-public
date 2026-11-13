"""Recover editable native objects without sacrificing the rest of a page.

Every accepted object has complete PDF character provenance and is checked against
an independent office render. Unaccepted objects stay in the source background.
This is partial editability, never a claim that all PDF text was reconstructed.
"""
from collections import defaultdict
from contextlib import closing
from copy import deepcopy
import ctypes
from io import BytesIO
import math
import os
import statistics
import re
import shutil
from pathlib import Path
import tempfile
import time
import unicodedata
import numpy as np
import pypdfium2 as pdfium
from PIL import Image
from pptx import Presentation
from pptx.util import Pt
from .layout import extract_native, merge_native_runs, page_background, add_background, add_text
from .pdf import render_page
from .render_gate import render_presentations
from .selected_render import render_selected,location,page_image


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


def word_pixel_box(box,page_size):
    """Use the same bounded raster grid for selection and background editing."""
    w,h=page_size;scale=min(2.0,2200/max(w,h));width,height=math.ceil(w*scale),math.ceil(h*scale)
    l,b,r,t=box
    return max(0,math.floor(l*scale)-2),max(0,math.floor((h-t)*scale)-2),min(width,math.ceil(r*scale)+2),min(height,math.ceil((h-b)*scale)+2)


def intersects(a,b):
    return a[0]<b[2] and b[0]<a[2] and a[1]<b[3] and b[1]<a[3]


def objects_for_page(page,grouped=True,word_regions=False,word_clusters=False,cluster_mode='adjacent',normalize_tails=False):
    if word_clusters and not word_regions:raise ValueError("word clusters require regional words")
    if normalize_tails and not (word_clusters and cluster_mode=='collision'):raise ValueError("tail normalization requires complete collision components")
    runs,objects,warnings=extract_native(page,split_words=word_regions,allow_quarter_turns=word_regions,partial_regions=word_regions);groups=defaultdict(list)
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
    if word_regions:
        # Recover words independently while retaining all unselected glyphs of
        # the same PDF object in the raster. Touching padded boxes are ambiguous.
        regions=[];parts=[(obj,run) for obj,runs in safe for run in runs]
        if word_clusters:
            from .word_clusters import MAX_PAGE_RUNS
            if len(parts)>MAX_PAGE_RUNS:return [],sorted(set(warnings+['word_cluster_resource_limit']))
        blocked={tuple(box) for _,run in parts for box in run.get('blocked_boxes',[])}
        blocked_pixels=[word_pixel_box(box,page.get_size()) for box in blocked]
        boxes=[word_pixel_box(r['box'],page.get_size()) for _,r in parts];cells=defaultdict(set)
        memberships=[]
        for i,(l,t,r,b) in enumerate(boxes):
            keys=[(x,y) for x in range(l//64,(r-1)//64+1) for y in range(t//64,(b-1)//64+1)]
            memberships.append(keys)
            for key in keys:cells[key].add(i)
        if word_clusters:
            if page.get_rotation():return [],warnings
            from .word_clusters import connected_word_clusters,source_verified,bounded_neighbors,MAX_SOURCE_CHARS
            # Any non-candidate visible source character is a protected obstacle,
            # including unsafe objects not represented in the safe run list.
            origin_x,origin_y,_,_=page.get_bbox()
            with closing(page.get_textpage()) as tp:
                if tp.count_chars()>MAX_SOURCE_CHARS:return [],sorted(set(warnings+['word_cluster_resource_limit']))
                admitted={i for _,run in parts for i in range(run['index'],run['end_index'])}
                for i in range(tp.count_chars()):
                    if i in admitted:continue
                    code=pdfium.raw.FPDFText_GetUnicode(tp,i)
                    if not code or chr(code).isspace():continue
                    l,b,r,t=tp.get_charbox(i)
                    box=(l-origin_x,b-origin_y,r-origin_x,t-origin_y)
                    if all(math.isfinite(v) for v in box) and box[2]>box[0] and box[3]>box[1]:
                        blocked_pixels.append(word_pixel_box(box,page.get_size()))
            neighbors=bounded_neighbors(memberships,cells)
            if neighbors is None:return [],sorted(set(warnings+['word_cluster_resource_limit']))
            clusters=connected_word_clusters(parts,boxes,neighbors,blocked_pixels,mode=cluster_mode)
            if normalize_tails:
                from .word_clusters import trim_generated_tails
                # Normalize only after the complete original spatial graph was
                # built. Never split components or weaken exact source owners.
                clusters=[(group,trim_generated_tails(page,runs)) for group,runs in clusters]
                clusters=[(group,runs) for group,runs in clusters if any(r.get('generated_tail_space_trimmed') for r in runs)]
            return [(group,runs) for group,runs in clusters if source_verified(page,runs)],warnings
        for i,(obj,run) in enumerate(parts):
            if any(intersects(boxes[i],box) for box in blocked_pixels):continue
            neighbors=set().union(*(cells[key] for key in memberships[i]))
            if any(i!=j and intersects(boxes[i],boxes[j]) for j in neighbors):continue
            regions.append(([obj],[dict(run,source_region=True)]))
        regions.sort(key=lambda item:item[1][0]['index'])
        return regions,warnings
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


def regional_background(page,objects):
    unique={ctypes.cast(obj.raw,ctypes.c_void_p).value:obj for group,_ in objects for obj in group}
    removed=page_background(page,list(unique.values()),max_side=2200,scale_limit=2.0)
    if not any(run.get('source_region') for _,runs in objects for run in runs):return removed
    # Removing a source text object in a scratch render supplies the real
    # underlying graphics. Copy only verified, nonoverlapping word regions;
    # outside those rectangles the original raster remains pixel-identical.
    original=page_background(page,[],max_side=2200,scale_limit=2.0)
    for _,runs in objects:
        for run in runs:
            if not run.get('source_region'):raise ValueError('mixed regional removal modes')
            box=word_pixel_box(run['box'],page.get_size())
            original.paste(removed.crop(box),box[:2])
    return original


def extension_seed(prs,slide,page,rendered=None,number=1):
    """Only extend our own simple raster-plus-text layout, preserving its XML."""
    if not slide.shapes or not all(s.has_text_frame for s in list(slide.shapes)[1:]):return None
    picture=slide.shapes[0]
    if not hasattr(picture,'image') or picture.rotation or any((picture.crop_left,picture.crop_right,picture.crop_top,picture.crop_bottom)):return None
    w,h=page.get_size();sw,sh=prs.slide_width/12700,prs.slide_height/12700
    scale=min(sw/w,sh/h);ox=(sw-w*scale)/2;oy=(sh-h*scale)/2
    if max(abs(a-b) for a,b in zip((picture.left/12700,picture.top/12700,picture.width/12700,picture.height/12700),(ox,oy,w*scale,h*scale)))>.001:return None
    with Image.open(BytesIO(picture.image.blob)) as image:background=image.convert('RGB').copy()
    raster_scale=min(2.0,2200/max(w,h))
    if background.size!=(math.ceil(w*raster_scale),math.ceil(h*raster_scale)):return None
    observed=None
    if rendered is not None:
        from .ocr_fit import observed_boxes
        targets=[{'shape':i,'bbox':(s.left/12700,s.top/12700,(s.left+s.width)/12700,(s.top+s.height)/12700)}
                 for i,s in enumerate(slide.shapes) if s.has_text_frame]
        path,index=location(rendered,number)
        with pdfium.PdfDocument(path) as doc,closing(doc[index]) as actual:observed=observed_boxes(actual,slide,targets)
        if len(observed)!=len(targets):return None
    protected=[];protected_points=[]
    for i,shape in enumerate(list(slide.shapes)[1:],1):
        x,y,width,height=(v/12700 for v in (shape.left,shape.top,shape.width,shape.height))
        angle=math.radians(shape.rotation);c,s=abs(math.cos(angle)),abs(math.sin(angle))
        rw,rh=width*c+height*s,width*s+height*c;cx,cy=x+width/2,y+height/2
        l,t,r,b=observed[i] if observed is not None else (cx-rw/2,cy-rh/2,cx+rw/2,cy+rh/2)
        protected_points.append((l,t,r,b))
        # Patches must not touch the retained textbox, including its rotation.
        protected.append(((l-ox)/scale*raster_scale-2,(t-oy)/scale*raster_scale-2,
                          (r-ox)/scale*raster_scale+2,(b-oy)/scale*raster_scale+2))
    return {'background':background,'shapes':[deepcopy(s._element) for s in list(slide.shapes)[1:]],
            'protected':protected,'protected_points':protected_points}


def retained_pixels_unchanged(seed,baseline,actual,prs):
    """An extension may not cover or alter the verified text it retains."""
    if baseline.size!=actual.size:return False
    for box in seed['protected_points']:
        bounds=region_box(box,actual.size,prs)
        if bounds is None or baseline.crop(bounds).tobytes()!=actual.crop(bounds).tobytes():return False
    return True


def extension_candidates(page,objects,prior,seed):
    # Source occurrences, rather than identical text elsewhere, determine overlap.
    return [obj for obj in objects
            if not any(prior.intersection(range(r['index'],r['end_index'])) for r in obj[1])
            and not any(intersects(word_pixel_box(r['box'],page.get_size()),b) for r in obj[1] for b in seed['protected'])]


def draw_objects(prs,slide,page,objects,seed=None):
    for shape in list(slide.shapes):shape._element.getparent().remove(shape._element)
    w,h=page.get_size();sw,sh=prs.slide_width/12700,prs.slide_height/12700
    scale=min(sw/w,sh/h);ox=(sw-w*scale)/2;oy=(sh-h*scale)/2
    # Match the content gate's source-image sampling. Otherwise untouched parts
    # of the page acquire new antialiasing and fail the whole-page comparison.
    background=regional_background(page,objects)
    if seed is not None:
        patched=seed['background'].copy()
        for _,runs in objects:
            for run in runs:
                box=word_pixel_box(run['box'],page.get_size())
                patched.paste(background.crop(box),box[:2])
        background=patched
    add_background(slide,background,w*scale,h*scale,(ox,oy))
    if seed is not None:
        for element in seed['shapes']:slide.shapes._spTree.insert_element_before(deepcopy(element),'p:extLst')
    regions=[]
    for _,runs in objects:
        boxes=[]
        for run in runs:
            l,b,r,t=run['box'];fs=run['size']
            shape=add_text(slide,run['text'],ox+l*scale,oy+(h-t-fs*.18)*scale,
                (r-l+fs*.3)*scale,fs*1.5*scale,fs*scale,run['font'],run['bold'],run['color'],italic=run['italic'])
            angle=run.get('rotation',0)
            if angle:
                width=((t-b) if angle in (90,270) else (r-l))*scale+fs*.3*scale
                height=fs*1.5*scale;cx=ox+(l+r)*scale/2;cy=oy+(h-(t+b)/2)*scale
                shape.left=Pt(cx-width/2);shape.top=Pt(cy-height/2);shape.width=Pt(width);shape.height=Pt(height);shape.rotation=angle
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


def rendered_word_regions(prs,number,page,objects,rendered,shape_offset=0):
    """Bound actual rendered glyphs, not the textbox's empty line-height area.

    Text must be found once near its source location, and every edge must be
    within 2pt. Including both source and output ink catches displacement.
    """
    from .ocr_fit import observed_boxes
    w,h=page.get_size();sw,sh=prs.slide_width/12700,prs.slide_height/12700
    scale=min(sw/w,sh/h);ox=(sw-w*scale)/2;oy=(sh-h*scale)/2
    targets=[]
    for _,runs in objects:
        for run in runs:
            l,b,r,t=run['box'];targets.append({'shape':len(targets)+1+shape_offset,'bbox':(ox+l*scale,oy+(h-t)*scale,ox+r*scale,oy+(h-b)*scale)})
    path,index=location(rendered,number)
    with pdfium.PdfDocument(path) as doc,closing(doc[index]) as actual:
        found=observed_boxes(actual,prs.slides[number-1],targets)
    regions=[];index=0
    for _,runs in objects:
        boxes=[]
        for run in runs:
            row=targets[index];index+=1;desired=row['bbox'];observed=found.get(row['shape'])
            if observed is None or max(abs(a-b) for a,b in zip(desired,observed))>2:
                boxes.append(None);continue
            boxes.append((min(desired[0],observed[0]),min(desired[1],observed[1]),max(desired[2],observed[2]),max(desired[3],observed[3])))
        regions.append(boxes if all(b is not None for b in boxes) else None)
    return regions


def character_height_ratio(page,run,needle,observed,scale):
    """Match complete one-to-one source glyphs before measuring optical height.

    Keep the word atomic. Raw source boxes are only comparable on unrotated
    pages; Unicode expansions and unresolved provenance are not measurements.
    """
    if page.get_rotation() or run.get('rotation'):return None
    source=[]
    with closing(page.get_textpage()) as tp:
        start,end=run['index'],run['end_index']
        if not 0<=start<end<=tp.count_chars():return None
        for i in range(start,end):
            code=pdfium.raw.FPDFText_GetUnicode(tp,i)
            if not code or code in (0xfffd,0xfffe,0xffff):return None
            char=chr(code)
            if char.isspace():continue
            normalized=unicodedata.normalize('NFKC',char)
            if len(normalized)!=1 or unicodedata.category(char) in ('Cc','Co','Cs'):return None
            obj=tp.get_textobj(i)
            if obj is None or ctypes.cast(obj.raw,ctypes.c_void_p).value!=run['object_id']:return None
            source.append((normalized,tp.get_charbox(i)))
    if len(source)!=len(observed) or ''.join(c for c,_ in source)!=needle:return None
    ratios=[]
    for (_,a),b in zip(source,observed):
        if not all(math.isfinite(v) for v in (*a,*b)):return None
        ah,bh=a[3]-a[1],b[3]-b[1]
        if min(ah,bh)<=.1:return None
        ratios.append(ah*scale/bh)
    return statistics.median(ratios) if ratios else None


def calibrate_runs(prs, number, page, objects, rendered,trim_spacing=False,shape_offset=0,character_fit=False):
    """Measure the office renderer's glyph placement, then fit source ink bounds.

    Numeric/character content is never edited. Ambiguous or implausible matches
    remain uncalibrated and must still pass the independent pixel gate.
    """
    w,h=page.get_size();sw,sh=prs.slide_width/12700,prs.slide_height/12700
    scale=min(sw/w,sh/h);ox=(sw-w*scale)/2;oy=(sh-h*scale)/2
    path,index=location(rendered,number)
    with pdfium.PdfDocument(path) as doc,closing(doc[index]) as actual,closing(actual.get_textpage()) as tp:
        from .ocr_fit import observed_boxes,fit_shape
        flat=[r for _,runs in objects for r in runs];targets=[]
        for i,run in enumerate(flat,1+shape_offset):
            if not run.get('rotation'):continue
            l,b,r,t=run['box'];targets.append({'shape':i,'bbox':(ox+l*scale,oy+(h-t)*scale,ox+r*scale,oy+(h-b)*scale)})
        rotated=observed_boxes(actual,prs.slides[number-1],targets) if targets else {}
        chars=[];boxes=[]
        for i in range(tp.count_chars()):
            code=pdfium.raw.FPDFText_GetUnicode(tp,i)
            if not code:continue
            value=unicodedata.normalize('NFKC',chr(code))
            for c in value:
                if not c.isspace():chars.append(c);boxes.append(tp.get_charbox(i))
        text=''.join(chars);used=set()
        shapes=iter([s for s in prs.slides[number-1].shapes if s.has_text_frame][shape_offset:])
        shape_index=shape_offset
        for _,runs in objects:
            for run in runs:
                shape=next(shapes);shape_index+=1
                needle=''.join(unicodedata.normalize('NFKC',run['text']).split())
                if not needle:continue
                l,b,r,t=run['box'];desired=(ox+l*scale,oy+(h-t)*scale,ox+r*scale,oy+(h-b)*scale)
                if run.get('rotation'):
                    observed=rotated.get(shape_index)
                    if observed is not None and fit_shape(shape,desired,observed):
                        font=shape.text_frame.paragraphs[0].runs[0]
                        run['fit']={'x':shape.left/12700,'y':shape.top/12700,'width':shape.width/12700,'height':shape.height/12700,
                                    'size':font.font.size/12700,'spacing':int(font._r.get_or_add_rPr().get('spc','0'))}
                    continue
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
                if character_fit:
                    ratio=character_height_ratio(page,run,needle,boxes[start:end],scale)
                    if ratio is None:continue
                # Nominal point sizes are not comparable across font families:
                # CJK faces can have much taller Latin capitals. Allow bounded
                # optical sizing; final 2pt glyph and pixel gates are unchanged.
                count=len(run['text'].strip()) if trim_spacing else len(run['text'])
                if not .65<=ratio<=1.5:continue
                single=trim_spacing and count==1
                if single:
                    if abs(dw-aw*ratio)>4:continue
                elif not .7<=dw/(aw*ratio)<=1.3:continue
                spacing=0 if single else (dw-aw*ratio)/max(1,count-1)
                size=shape.text_frame.paragraphs[0].runs[0].font.size/12700*ratio
                if abs(spacing)>size*.2:continue
                run['fit']={'x':desired[0]+((dw-aw*ratio)/2 if single else 0)-(observed[0]-shape.left/12700)*ratio,
                    'y':desired[1]-(observed[1]-shape.top/12700)*ratio,
                    'width':dw+size,'height':size*1.8,'size':size,'spacing':round(spacing*100)}
                if character_fit:run['fit']['calibration_mode']='median-character-height'


def covered_source_indices(page, objects):
    """Bind editability to actual source glyph occurrences, not a text multiset."""
    with closing(page.get_textpage()) as tp:
        indices=set()
        for _,runs in objects:
            for run in runs:
                owners=set(run.get('object_ids',[run['object_id']]))
                for i in range(run['index'],run['end_index']):
                    code=pdfium.raw.FPDFText_GetUnicode(tp,i)
                    if not code or chr(code).isspace():continue
                    obj=tp.get_textobj(i)
                    if obj is not None and ctypes.cast(obj.raw,ctypes.c_void_p).value in owners:indices.add(i)
        return indices


def compact_source_ranges(indices):
    ranges=[]
    for index in sorted(indices):
        if ranges and ranges[-1][1]==index:ranges[-1][1]=index+1
        else:ranges.append([index,index+1])
    return ranges


def alternative_base_sans(objects):
    """Try a reviewed substitute, never assert identity with an uploaded font.

    Restrict to observed regular Helvetica names, full raw/NFKC cmap coverage,
    and existing isolated-word ownership. Every accepted word still passes the
    unchanged geometry, region, retained-pixel and whole-page checks.
    """
    from .base_font import FAMILY,approved_cmap
    cmap=approved_cmap();selected=[]
    for group,runs in objects:
        if not runs:continue
        def eligible(run):
            name=re.sub(r'^[A-Z]{6}\+','',run.get('source_base_font',''))
            text=run['text']
            return (name in {'Helvetica','HelveticaNeueLTStd-Roman'} and
                    not run['bold'] and not run['italic'] and not run.get('rotation') and
                    run['font']!=FAMILY and bool(text.strip()) and
                    all(ord(c) in cmap or c in '\t\r\n' for c in text+unicodedata.normalize('NFKC',text)))
        if all(eligible(run) for run in runs):
            selected.append((group,[dict(run,font=FAMILY,substituted=True) for run in runs]))
    return selected


def alternative_cmu_light(objects):
    """Explicit regular typewriter sources only; substitute, not font identity."""
    from .light_font import FAMILY,approved_cmap
    def eligible(run):
        name=re.sub(r'^[A-Z]{6}\+','',run.get('source_base_font','')).lower().replace(' ','')
        return (bool(re.fullmatch(r'(?:sftt\d{4}|cmtt\d+|cmutypewritertext(?:[-,]regular)?)',name)) and
                run['font']=='CMU Typewriter Text' and not run.get('rotation') and
                not run['bold'] and not run['italic'] and bool(run['text'].strip()))
    possible=[(group,runs) for group,runs in objects if runs and all(eligible(run) for run in runs)]
    if not possible:return []
    # Validate once per candidate pass, not once per word. Actual renderer and
    # embedding revalidate the operator bytes again before using the font.
    cmap=approved_cmap()
    return [(group,[dict(run,font=FAMILY,substituted=True) for run in runs])
            for group,runs in possible if all(all(ord(c) in cmap for c in
                run['text']+unicodedata.normalize('NFKC',run['text'])) for run in runs)]


def _screen_complete_components(objects,flags):
    """Unknown assessment shape rejects the page; never admit part of a group."""
    if (not isinstance(flags,list) or len(flags)!=sum(len(runs) for _,runs in objects)
            or any(type(flag) is not bool for flag in flags)):
        return []
    kept=[];cursor=0
    for obj in objects:
        count=len(obj[1])
        if count and all(flags[cursor:cursor+count]):kept.append(obj)
        cursor+=count
    return kept


def _recover_regions(source, target, page_numbers, settings,grouped=False,word_regions=False,minimum_coverage=None,extend=False,spacing_retry=False,character_fit=False,alternative_font=None,word_clusters=False,cluster_mode='adjacent',light_shift=0,light_guard_deadline=None,normalize_tails=False,tail_guard_deadline=None):
    """Mutate only verified pages. Renderer errors leave the caller's fallback intact."""
    if not page_numbers:return {}
    if extend and not word_regions:raise ValueError('extensions require regional words')
    if normalize_tails and not (extend and word_clusters and cluster_mode=='collision' and alternative_font is None and spacing_retry):
        raise ValueError('normalized tails require additive original-font collision recovery')
    if word_clusters and not (extend and word_regions):raise ValueError('word clusters require additive regional recovery')
    if character_fit and not (extend and spacing_retry):raise ValueError('character fitting requires additive spacing extension')
    if alternative_font is not None and (alternative_font not in ('base-sans','cmu-light') or not (extend and spacing_retry)):
        raise ValueError('alternative font requires approved additive spacing extension')
    if light_shift not in (0,.1) or (light_shift and alternative_font!='cmu-light'):
        raise ValueError('unsupported optional Light vertical trial')
    if alternative_font=='cmu-light' and light_guard_deadline is not None and time.monotonic()>=light_guard_deadline:return {}
    if normalize_tails and tail_guard_deadline is not None and time.monotonic()>=tail_guard_deadline:return {}
    reports={};minimum_coverage=minimum_coverage or {}
    prior={n:{i for a,b in report['source_ranges'] for i in range(a,b)} for n,report in minimum_coverage.items()}
    with tempfile.TemporaryDirectory(prefix='smartppt-regions-',dir=Path(source).parent) as tmp,pdfium.PdfDocument(source) as doc:
        folder=Path(tmp);prs=Presentation(target);pages={};candidates={};regions={};seeds={}
        baseline=folder/'baseline.pptx';shutil.copyfile(target,baseline)
        baseline_pdf=None
        selection=tuple(sorted(set(page_numbers)))
        def render(files):
            if len(selection)<len(doc):return render_selected(files,folder,settings,selection)
            return render_presentations(files,folder,settings)
        def draw(presentation,number,objects):
            return draw_objects(presentation,presentation.slides[number-1],pages[number],objects,**({'seed':seeds[number]} if number in seeds else {}))
        def geometry(presentation,number,objects,rendered):
            return rendered_word_regions(presentation,number,pages[number],objects,rendered,**({'shape_offset':len(seeds[number]['shapes'])} if number in seeds else {}))
        # Keep page handles alive: PDF object identities must not cross a reopen.
        try:
            for number in page_numbers:
                page=pages[number]=doc[number-1]
                if (character_fit or alternative_font) and page.get_rotation():continue
                objects,warnings=objects_for_page(page,grouped=grouped,word_regions=word_regions,**({'word_clusters':True,'cluster_mode':cluster_mode,**({'normalize_tails':True} if normalize_tails else {})} if word_clusters else {}))
                if word_clusters and 'word_cluster_resource_limit' in warnings:
                    previous=minimum_coverage.get(number)
                    if previous is not None and 'word_cluster_resource_limit' not in previous['warnings']:
                        previous['warnings'].append('word_cluster_resource_limit')
                    continue
                if alternative_font:
                    objects=(alternative_base_sans if alternative_font=='base-sans' else alternative_cmu_light)(objects)
                if character_fit:objects=[(group,runs) for group,runs in objects if not any(r.get('rotation') for r in runs)]
                if extend:
                    if number not in prior:continue
                    if not covered_source_indices(page,objects)-prior[number]:continue
                    if baseline_pdf is None:baseline_pdf=render([baseline])[0]
                    seed=extension_seed(prs,prs.slides[number-1],page,baseline_pdf,number)
                    if seed is None:continue
                    seeds[number]=seed;objects=extension_candidates(page,objects,prior[number],seed)
                if number in prior:
                    potential=covered_source_indices(page,objects)
                    if extend:potential|=prior[number]
                    if not prior[number]<potential:continue
                if objects:
                    candidates[number]=objects
                    regions[number]=draw(prs,number,objects)
            if not candidates:return {}
            candidate=folder/'candidate.pptx';prs.save(candidate)
            if extend:rendered=render([candidate])[0]
            else:baseline_pdf,rendered=render([baseline,candidate])
            for number,objects in list(candidates.items()):
                calibrate_runs(prs,number,pages[number],objects,rendered,**({'shape_offset':len(seeds[number]['shapes']),'trim_spacing':spacing_retry,'character_fit':character_fit} if extend else {}))
                if light_shift:
                    objects=[(group,runs) for group,runs in objects if all(r.get('fit') for r in runs)]
                    for _,runs in objects:
                        for run in runs:run['fit']['y']+=light_shift
                    if objects:candidates[number]=objects
                    else:candidates.pop(number,None)
                if character_fit:
                    objects=[(group,runs) for group,runs in objects if all(r.get('fit',{}).get('calibration_mode')=='median-character-height' for r in runs)]
                    if objects:candidates[number]=objects
                    else:candidates.pop(number,None)
                regions[number]=draw(prs,number,objects)
            if not candidates:return {}
            calibrated=folder/'calibrated.pptx';prs.save(calibrated)
            rendered=render([calibrated])[0]
            selected={};scores={}
            for number,objects in candidates.items():
                if word_regions:regions[number]=geometry(prs,number,objects,rendered)
                actual=page_image(rendered,number,max_side=1800)
                expected=aligned_source(pages[number],actual.size)
                chosen=[];measurements=[]
                for obj,boxes in zip(objects,regions[number]):
                    measured=score_regions(expected,actual,boxes,prs) if boxes else None
                    if measured:chosen.append(obj);measurements.extend(measured)
                if chosen:selected[number]=chosen;scores[number]=measurements
            if not selected:return {}
            # Rebuild from the pre-recovery package: failed pages must not inherit
            # any unverified candidate shapes or newly referenced images.
            final=Presentation(target);fallback=Presentation(target)
            for number,objects in selected.items():
                draw(final,number,objects)
            verified=folder/'verified.pptx';final.save(verified)
            final_pdf=render([verified])[0]
            if word_regions:
                # A selected word can interact with a neighboring word left as
                # raster. Prune failures and re-render; never approve a changed
                # set using the previous set's measurements.
                for iteration in range(2):
                    changed=False
                    for number,objects in list(selected.items()):
                        actual=page_image(final_pdf,number,max_side=1800)
                        expected=aligned_source(pages[number],actual.size)
                        boxes=geometry(final,number,objects,final_pdf)
                        kept=[obj for obj,box in zip(objects,boxes) if box and score_regions(expected,actual,box,final)]
                        if len(kept)==len(objects):continue
                        changed=True
                        if kept:
                            selected[number]=kept;draw(final,number,kept)
                        else:
                            del selected[number]
                            slide=final.slides[number-1]
                            for shape in list(slide.shapes):shape._element.getparent().remove(shape._element)
                            for shape in fallback.slides[number-1].shapes:
                                slide.shapes._spTree.insert_element_before(deepcopy(shape._element),'p:extLst')
                    if not changed:break
                    verified=folder/f'pruned-{iteration}.pptx';final.save(verified)
                    final_pdf=render([verified])[0]
            if normalize_tails and selected:
                from .light_visual_guard import assess
                changed=False
                for number,objects in list(selected.items()):
                    old_path,old_index=location(baseline_pdf,number)
                    new_path,new_index=location(final_pdf,number)
                    flags=assess(source,number-1,old_path,old_index,new_path,new_index,
                                 pages[number].get_size(),[run['box'] for _,runs in objects for run in runs],
                                 timeout=min(120,tail_guard_deadline-time.monotonic()) if tail_guard_deadline is not None else 120)
                    kept=_screen_complete_components(objects,flags)
                    if len(kept)==len(objects):continue
                    changed=True
                    if kept:selected[number]=kept;draw(final,number,kept)
                    else:
                        del selected[number]
                        slide=final.slides[number-1]
                        for shape in list(slide.shapes):shape._element.getparent().remove(shape._element)
                        for shape in fallback.slides[number-1].shapes:
                            slide.shapes._spTree.insert_element_before(deepcopy(shape._element),'p:extLst')
                if not selected:return {}
                if changed:
                    verified=folder/'tail-filtered.pptx';final.save(verified)
                    final_pdf=render([verified])[0]
            # A second whole-page check catches interactions between text objects,
            # clipping, shared resources and pixels outside their measured boxes.
            for number,objects in selected.items():
                coverage=covered_source_indices(pages[number],objects)
                if extend:coverage|=prior[number]
                improves=number not in prior or prior[number]<coverage
                actual=page_image(final_pdf,number,max_side=1800)
                expected=aligned_source(pages[number],actual.size)
                score=pixel_score(expected,actual)
                baseline_image=page_image(baseline_pdf,number,max_side=1800)
                baseline_score=pixel_score(expected,baseline_image)
                # Several bounded retries must not accumulate the page-error
                # allowance. Every replacement/extension uses the first gate's
                # source comparison, while retention checks use the last PPT.
                gate_baseline=minimum_coverage.get(number,{}).get('baseline_render',baseline_score)
                final_scores=[];regions_valid=True
                if extend:regions_valid=retained_pixels_unchanged(seeds[number],baseline_image,actual,final)
                if word_regions:
                    for boxes in geometry(final,number,objects,final_pdf):
                        measured=score_regions(expected,actual,boxes,final) if boxes else None
                        if measured:final_scores.extend(measured)
                        else:regions_valid=False
                if regions_valid and (alternative_font=='cmu-light' or normalize_tails):
                    from .light_visual_guard import verify
                    old_path,old_index=location(baseline_pdf,number)
                    new_path,new_index=location(final_pdf,number)
                    deadline=tail_guard_deadline if normalize_tails else light_guard_deadline
                    regions_valid=verify(source,number-1,old_path,old_index,new_path,new_index,
                                         pages[number].get_size(),[run['box'] for _,runs in objects for run in runs],
                                         timeout=min(120,deadline-time.monotonic()) if deadline is not None else 120)
                if not improves or not regions_valid or not acceptable_page(gate_baseline,score):
                    slide=final.slides[number-1]
                    for shape in list(slide.shapes):shape._element.getparent().remove(shape._element)
                    for shape in fallback.slides[number-1].shapes:
                        slide.shapes._spTree.insert_element_before(deepcopy(shape._element),'p:extLst')
                    continue
                if word_regions:scores[number]=final_scores
                runs=[run for _,parts in objects for run in parts]
                object_count=lambda items:len({ctypes.cast(obj.raw,ctypes.c_void_p).value for group,_ in items for obj in group})
                reports[number]={'route':'native-regions','editable_runs':len(runs),'editable_objects':object_count(objects),
                    'candidate_objects':object_count(candidates[number]),'candidate_regions':len(candidates[number]),'source_text_characters':sum(len(r['text']) for r in runs),
                    'regional_strategy':'source-words' if word_regions else 'joined-glyphs' if grouped else 'source-objects',
                    'source_run_indices':[run['index'] for run in runs],
                    'source_ranges':compact_source_ranges(coverage),
                    'covered_source_glyphs':len(coverage),
                    'font_substitutions':sorted({r['source_font']+' → '+r['font'] for r in runs if r['substituted']}),
                    'region_scores':scores[number],'final_render':score,'baseline_render':gate_baseline,
                    'warnings':['partial_native_editability','unrecovered_content_kept_as_graphic'],
                    'graphics':'raster; not editable'}
                if extend:
                    previous=minimum_coverage[number];report=reports[number]
                    report['warnings']=list(dict.fromkeys(previous.get('warnings',[])+report['warnings']))
                    report['regional_strategy']='source-word-clusters-extended' if word_clusters else 'source-words-extended'
                    if word_clusters:
                        report['added_word_clusters']=len(objects)
                        report['word_cluster_mode']=cluster_mode
                    report['extension_spacing_retry']=spacing_retry
                    report['extension_calibration_mode']='median-character-height' if character_fit else 'word-bounds'
                    if normalize_tails:
                        report['normalized_tail_cross_renderer_dpis']=[144,216,288,432]
                        report['omitted_generated_separator_indices']=sorted(r['source_original_end_index']-1 for r in runs if r.get('generated_tail_space_trimmed'))
                        warning='inferred_terminal_spaces_omitted_from_separate_textboxes'
                        if warning not in report['warnings']:report['warnings'].append(warning)
                    if alternative_font:
                        if alternative_font=='base-sans':
                            from .base_font import FAMILY
                        else:
                            from .light_font import FAMILY
                        report['extension_font_strategy']=alternative_font+'-substitute'
                        report['calibration_font']=FAMILY
                        if alternative_font=='cmu-light':
                            report['light_vertical_trial_points']=light_shift
                            report['light_cross_renderer_dpis']=[144,216,288,432]
                        if 'reviewed_font_substitute_not_source_identity' not in report['warnings']:
                            report['warnings'].append('reviewed_font_substitute_not_source_identity')
                    report['retained_regions']=deepcopy(previous)
                    report['added_source_ranges']=compact_source_ranges(coverage-prior[number])
                    report['added_editable_runs']=len(runs)
                    report['source_run_indices']=previous['source_run_indices']+report['source_run_indices']
                    report['editable_runs']+=previous['editable_runs']
                    report['source_text_characters']+=previous['source_text_characters']
                    # Objects may contribute both retained and added words.
                    with closing(pages[number].get_textpage()) as textpage:
                        report['editable_objects']=len({ctypes.cast(obj.raw,ctypes.c_void_p).value for i in coverage if (obj:=textpage.get_textobj(i)) is not None})
                    report['font_substitutions']=sorted(set(report['font_substitutions']+previous['font_substitutions']))
            if reports:final.save(target)
        finally:
            for page in pages.values():page.close()
    return reports


def recover_regions(source,target,page_numbers,settings):
    """Improve partial pages without losing any previously verified source glyph.

    A footer alone must not stop the finer-grained body recovery attempts.
    Each pass still checks its regions, its final render and source coverage.
    """
    from .config import ConversionError
    reports=_recover_regions(source,target,page_numbers,settings,grouped=False)
    for option,label in [('grouped','grouped'),('word_regions','word')]:
        try:reports.update(_recover_regions(source,target,page_numbers,settings,minimum_coverage=reports,**{option:True}))
        except ConversionError:
            if not reports:raise
            for report in reports.values():report['warnings'].append(f'additional_{label}_recovery_unavailable')
            break
    # A rejected replacement must not discard disjoint words that could safely
    # extend the verified package. Keep every existing textbox byte-for-byte.
    # Even an accepted word pass used untrimmed spacing; the bounded
    # extension can add disjoint words without replacing any verified glyph.
    remaining=[n for n,r in reports.items() if r.get('source_ranges')]
    if remaining:
        for spacing_retry in (True,False):
            try:reports.update(_recover_regions(source,target,remaining,settings,word_regions=True,minimum_coverage=reports,extend=True,spacing_retry=spacing_retry))
            except ConversionError:
                for n in remaining:reports[n]['warnings'].append('additional_word_extension_unavailable')
                break
        # A single additional optical retry may add words, never replace the
        # verified package or restart the previous bounded extension loop.
        try:reports.update(_recover_regions(source,target,remaining,settings,word_regions=True,minimum_coverage=reports,extend=True,spacing_retry=True,character_fit=True))
        except ConversionError:
            for n in remaining:reports[n]['warnings'].append('additional_character_extension_unavailable')
        # Two bounded substitute-font attempts extend the same verified package;
        # neither can remove an earlier accepted source occurrence or shape.
        for character_fit in (True,False):
            try:reports.update(_recover_regions(source,target,remaining,settings,word_regions=True,minimum_coverage=reports,extend=True,spacing_retry=True,character_fit=character_fit,alternative_font='base-sans'))
            except ConversionError:
                for n in remaining:reports[n]['warnings'].append('additional_base_sans_extension_unavailable')
                break
        # Full padded-box collision components are atomic: nearby lines remain
        # separate source-positioned textboxes, and each word keeps its gates.
        # Never split components or retry an unbounded sequence of alternatives.
        for alternative_font in (None,'base-sans'):
            if alternative_font and any('additional_base_sans_extension_unavailable' in r['warnings'] for r in reports.values()):continue
            for character_fit in (True,False):
                if character_fit and alternative_font is None and any('additional_character_extension_unavailable' in r['warnings'] for r in reports.values()):continue
                cluster_pages=[n for n in remaining if 'word_cluster_resource_limit' not in reports[n]['warnings']]
                if not cluster_pages:break
                try:reports.update(_recover_regions(source,target,cluster_pages,settings,word_regions=True,minimum_coverage=reports,extend=True,spacing_retry=True,character_fit=character_fit,alternative_font=alternative_font,word_clusters=True,cluster_mode='collision'))
                except ConversionError:
                    for n in remaining:
                        warning='additional_word_cluster_extension_unavailable'
                        if warning not in reports[n]['warnings']:reports[n]['warnings'].append(warning)
                    break
        # Optional regular Light substitute is additive only, after all prior
        # passes, and never changes an accepted textbox or source coverage.
        from .light_font import capability
        if capability():
            light_guard_deadline=time.monotonic()+120
            for character_fit,light_shift in ((True,0),(True,.1),(False,0),(False,.1)):
                if time.monotonic()>=light_guard_deadline:break
                try:reports.update(_recover_regions(source,target,remaining,settings,word_regions=True,minimum_coverage=reports,extend=True,spacing_retry=True,character_fit=character_fit,alternative_font='cmu-light',light_shift=light_shift,light_guard_deadline=light_guard_deadline))
                except ConversionError:
                    for n in remaining:reports[n]['warnings'].append('additional_cmu_light_extension_unavailable')
                    break
        # Generated separators never become source-authorized glyphs. Only a
        # copied, trimmed collision component may enter this final additive
        # stage; all members must pass four-DPI screening, then the rebuilt
        # combination is verified again. Existing accepted routes stay intact.
        if os.name=='posix' and shutil.which('pdftoppm'):
            tail_guard_deadline=time.monotonic()+120
            for character_fit in (True,False):
                if time.monotonic()>=tail_guard_deadline:break
                tail_pages=[n for n in remaining if 'word_cluster_resource_limit' not in reports[n]['warnings']]
                if not tail_pages:break
                try:reports.update(_recover_regions(source,target,tail_pages,settings,word_regions=True,minimum_coverage=reports,extend=True,spacing_retry=True,character_fit=character_fit,word_clusters=True,cluster_mode='collision',normalize_tails=True,tail_guard_deadline=tail_guard_deadline))
                except ConversionError:
                    for n in remaining:reports[n]['warnings'].append('additional_normalized_cluster_extension_unavailable')
                    break
    from .regional_order import restore_source_order
    restore_source_order(source,target,reports,settings)
    return reports

