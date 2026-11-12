"""Measure actual Office glyphs before accepting scan font/spacing correction."""
from contextlib import closing
from copy import deepcopy
import math,shutil,tempfile
from pathlib import Path
import pypdfium2 as pdfium
import numpy as np
from PIL import Image
from pptx import Presentation
from pptx.util import Pt
from .quality import normalized
from .render_gate import render_presentations,metric,accept_candidate


def observed_boxes(page,slide,targets):
    with closing(page.get_textpage()) as tp:
        chars=[];boxes=[]
        for i in range(tp.count_chars()):
            code=pdfium.raw.FPDFText_GetUnicode(tp,i)
            if not code:continue
            for char in normalized(chr(code)):
                chars.append(char);boxes.append(tp.get_charbox(i))
        text=''.join(chars);used=set();out={};height=page.get_height()
        for target in targets:
            shape=slide.shapes[target['shape']];needle=normalized(shape.text);matches=[];start=0
            if not needle:continue
            while (start:=text.find(needle,start))>=0:
                end=start+len(needle)
                if not used.intersection(range(start,end)):
                    bs=boxes[start:end];box=(min(b[0] for b in bs),height-max(b[3] for b in bs),max(b[2] for b in bs),height-min(b[1] for b in bs))
                    distance=sum(abs(a-b) for a,b in zip(target['bbox'],box))
                    matches.append((distance,start,end,box))
                start+=1
            if not matches and shape.rotation in (90,180,270):
                # PDFium can emit a rotated line in reversed *chunks*, while
                # its Unicode glyphs and positions are intact. Reconstruct only
                # an exact spatially bounded match, never reverse the string.
                cx=(shape.left+shape.width/2)/12700;cy=(shape.top+shape.height/2)/12700
                desired=local_box(target['bbox'],cx,cy,shape.rotation)
                margin=shape.text_frame.paragraphs[0].runs[0].font.size.pt*.75
                located=[]
                for j,box in enumerate(boxes):
                    if j in used:continue
                    l,b,r,t=box;top_box=(l,height-t,r,height-b)
                    local=local_box(top_box,cx,cy,shape.rotation);x,y=(local[0]+local[2])/2,(local[1]+local[3])/2
                    if desired[0]-margin<=x<=desired[2]+margin and desired[1]-margin<=y<=desired[3]+margin:
                        located.append((x,j,top_box))
                located.sort()
                if ''.join(chars[j] for _,j,_ in located)==needle:
                    bs=[b for _,_,b in located]
                    box=(min(b[0] for b in bs),min(b[1] for b in bs),max(b[2] for b in bs),max(b[3] for b in bs))
                    if sum(abs(a-b) for a,b in zip(target['bbox'],box))<=max(24,margin/0.75*4):
                        used.update(j for _,j,_ in located);out[target['shape']]=box
                continue
            if not matches:continue
            distance,start,end,box=min(matches)
            if distance>max(24,shape.text_frame.paragraphs[0].runs[0].font.size.pt*4):continue
            used.update(range(start,end));out[target['shape']]=box
        return out


def local_box(box,cx,cy,angle):
    angle=math.radians(angle);c,s=math.cos(angle),math.sin(angle)
    l,t,r,b=box;pts=[(cx+(x-cx)*c+(y-cy)*s,cy-(x-cx)*s+(y-cy)*c) for x,y in [(l,t),(r,t),(r,b),(l,b)]]
    return min(x for x,y in pts),min(y for x,y in pts),max(x for x,y in pts),max(y for x,y in pts)


def fit_shape(shape,desired,observed):
    # Quarter turns preserve rectangular glyph bounds. Small skew needs a
    # polygon-aware fitter; keep its current rendering unchanged here.
    if shape.rotation not in (0,90,180,270):return False
    cx=(shape.left+shape.width/2)/12700;cy=(shape.top+shape.height/2)/12700;angle=shape.rotation
    d=local_box(desired,cx,cy,angle);a=local_box(observed,cx,cy,angle)
    return fit_local(shape,d,a)


def fit_local(shape,d,a):
    cx=(shape.left+shape.width/2)/12700;cy=(shape.top+shape.height/2)/12700;angle=shape.rotation
    dw,dh=d[2]-d[0],d[3]-d[1];aw,ah=a[2]-a[0],a[3]-a[1]
    if min(dw,dh,aw,ah)<=0:return False
    ratio=dh/ah
    if not .8<=ratio<=1.2 or not .8<=dw/(aw*ratio)<=1.2:return False
    run=shape.text_frame.paragraphs[0].runs[0];size=run.font.size.pt*ratio
    props=run._r.get_or_add_rPr()
    spacing=int(props.get('spc','0'))/100*ratio+(dw-aw*ratio)/max(1,len(shape.text)-1)
    if abs(spacing)>size*.2:return False
    x=d[0]-(a[0]-shape.left/12700)*ratio;y=d[1]-(a[1]-shape.top/12700)*ratio
    width=dw+size;height=size*1.8
    nx,ny=x+width/2,y+height/2;c,s=math.cos(math.radians(angle)),math.sin(math.radians(angle))
    nx,ny=cx+(nx-cx)*c-(ny-cy)*s,cy+(nx-cx)*s+(ny-cy)*c
    shape.left=Pt(nx-width/2);shape.top=Pt(ny-height/2);shape.width=Pt(width);shape.height=Pt(height)
    run.font.size=Pt(size);run._r.get_or_add_rPr().set('spc',str(round(spacing*100)))
    return True


def raster_bounds(page,slide,targets,observed):
    """Measure actual ink in each unique text region after undoing its rotation.

    OCR text is still matched through the independent PDF text layer first.
    Reject ambiguous/noisy borders instead of fitting nearby graphics.
    """
    scale=min(2.0,2400/max(page.get_size()))
    with closing(page.render(scale=scale)) as bitmap:image=bitmap.to_pil().convert('RGB').copy()
    out={}
    for row in targets:
        n=row['shape']
        if n not in observed or not row.get('quad'):continue
        shape=slide.shapes[n];angle=shape.rotation;cx=(shape.left+shape.width/2)/12700;cy=(shape.top+shape.height/2)/12700
        c,s=math.cos(math.radians(angle)),math.sin(math.radians(angle))
        pts=[(cx+(x-cx)*c+(y-cy)*s,cy-(x-cx)*s+(y-cy)*c) for x,y in row['quad']]
        desired=(min(x for x,y in pts),min(y for x,y in pts),max(x for x,y in pts),max(y for x,y in pts))
        box=local_box(observed[n],cx,cy,angle)
        l,t,r,b=math.floor(box[0]*scale)-3,math.floor(box[1]*scale)-3,math.ceil(box[2]*scale)+3,math.ceil(box[3]*scale)+3
        if l<0 or t<0 or r>image.width or b>image.height:continue
        working=image.rotate(angle,resample=Image.Resampling.BICUBIC,center=(cx*scale,cy*scale),fillcolor='white') if angle else image
        crop=np.asarray(working.crop((l,t,r,b)),dtype=float);border=np.concatenate((crop[0],crop[-1],crop[:,0],crop[:,-1]));background=np.median(border,axis=0)
        if np.quantile(np.abs(border-background),.95)>12:continue
        mask=np.max(np.abs(crop-background),axis=2)>30;padded=np.pad(mask.astype(np.uint8),1)
        neighbors=sum(padded[y:y+mask.shape[0],x:x+mask.shape[1]] for y in range(3) for x in range(3));ink=np.argwhere(mask&(neighbors>=3))
        if not len(ink):continue
        actual=((l+int(ink[:,1].min()))/scale,(t+int(ink[:,0].min()))/scale,(l+int(ink[:,1].max())+1)/scale,(t+int(ink[:,0].max())+1)/scale)
        out[n]=(desired,actual)
    return out


def _fit_ocr_pages(source,target,report,settings,prefer_ink=False):
    with tempfile.TemporaryDirectory(prefix='smartppt-scan-fit-',dir=Path(source).parent) as tmp:
        tmp=Path(tmp);before=tmp/'before.pptx';candidate=tmp/'candidate.pptx';shutil.copyfile(target,before)
        baseline_pdf=render_presentations([before],tmp,settings)[0];prs=Presentation(target);changed={}
        with pdfium.PdfDocument(baseline_pdf) as doc:
            for item in report:
                if item['route']!='paddle-ocr' or not item.get('ink_targets'):continue
                index=item['page']-1;slide=prs.slides[index]
                with closing(doc[index]) as page:
                    observed=observed_boxes(page,slide,item['ink_targets'])
                    raster=raster_bounds(page,slide,item['ink_targets'],observed)
                originals={}
                for row in item['ink_targets']:
                    n=row['shape']
                    if n not in observed:continue
                    original=deepcopy(slide.shapes[n]._element)
                    # Fit actual ink using the same measurement as the source
                    # targets. Font boxes can include blank side bearings,
                    # particularly for CJK punctuation and italic glyphs.
                    shape=slide.shapes[n]
                    if prefer_ink:
                        # Already aligned glyphs need no second fit. Moving them
                        # can add raster noise and reject a useful correction
                        # elsewhere on the same page.
                        if n not in raster or max(abs(a-b) for a,b in zip(*raster[n]))<=2:continue
                        fitted=fit_local(shape,*raster[n])
                    else:fitted=fit_shape(shape,row['bbox'],observed[n]) if shape.rotation in (0,90,180,270) else (fit_local(shape,*raster[n]) if n in raster else False)
                    if fitted:originals[n]=original
                if originals:changed[index]=originals
        if not changed:return
        prs.save(candidate);rendered=render_presentations([candidate],tmp,settings)[0]
        with pdfium.PdfDocument(rendered) as doc:
            for item in report:
                index=item['page']-1
                if index not in changed:continue
                slide=prs.slides[index]
                with closing(doc[index]) as page:
                    actual=observed_boxes(page,slide,item['ink_targets'])
                    raster=raster_bounds(page,slide,item['ink_targets'],actual)
                rows=[r for r in item['ink_targets'] if r['shape'] in changed[index]]
                errors=[]
                for row in rows:
                    n=row['shape'];shape=slide.shapes[n]
                    if prefer_ink:error=max(abs(a-b) for a,b in zip(*raster[n])) if n in raster else None
                    elif shape.rotation in (0,90,180,270):
                        error=max(abs(a-b) for a,b in zip(row['bbox'],actual[n])) if n in actual else None
                    else:error=max(abs(a-b) for a,b in zip(*raster[n])) if n in raster else None
                    errors.append(error)
                old=metric(source,baseline_pdf,index);new=metric(source,rendered,index)
                accepted=all(e is not None and e<=2 for e in errors) and accept_candidate(old,new)
                item['font_fit_ink' if prefer_ink else 'font_fit']={'accepted':accepted,'candidate_lines':len(rows),'max_ink_error_points':max((e for e in errors if e is not None),default=None),'baseline':old,'candidate':new}
                if not accepted:
                    for n,element in changed[index].items():
                        current=slide.shapes[n]._element;current.getparent().replace(current,element)
        prs.save(target)


def fit_ocr_pages(source,target,report,settings):
    _fit_ocr_pages(source,target,report,settings)
    _fit_ocr_pages(source,target,report,settings,prefer_ink=True)
