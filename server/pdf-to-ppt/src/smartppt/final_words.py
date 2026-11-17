"""Check native word geometry in the finished, mixed presentation package."""
from collections import Counter
from contextlib import closing
from copy import deepcopy
from pathlib import Path
import math
import shutil
import tempfile
import pypdfium2 as pdfium
from pptx import Presentation
from .config import ConversionError
from .quality import normalized,shape_text
from .ocr_fit import observed_boxes,fit_shape
from .render_gate import render_presentations,metric,accept_candidate


def source_targets(prs,number,page):
    """Bind final text shapes to consecutive source glyphs, including script splits."""
    width,height=page.get_size();sw,sh=prs.slide_width/12700,prs.slide_height/12700
    scale=min(sw/width,sh/height);ox=(sw-width*scale)/2;oy=(sh-height*scale)/2
    origin_x,origin_y,_,_=page.get_bbox();rotation=page.get_rotation()
    def point(x,y):
        x-=origin_x;y-=origin_y
        if rotation==90:return y,height-x
        if rotation==180:return width-x,height-y
        if rotation==270:return width-y,x
        return x,y
    characters=[];boxes=[]
    with closing(page.get_textpage()) as tp:
        reference=normalized(tp.get_text_range())
        for i in range(tp.count_chars()):
            # PDFium can expose an unencoded graphic marker as U+0002 while
            # excluding it from the text stream. Bind only indexed source text;
            # do not invent a character for a glyph retained in the background.
            if pdfium.raw.FPDFText_GetTextIndexFromCharIndex(tp,i)<0:continue
            code=pdfium.raw.FPDFText_GetUnicode(tp,i)
            if not code:continue
            text=normalized(chr(code))
            if not text:continue
            l,b,r,t=tp.get_charbox(i)
            corners=[point(x,y) for x,y in [(l,b),(l,t),(r,b),(r,t)]]
            box=(ox+min(x for x,y in corners)*scale,oy+(height-max(y for x,y in corners))*scale,
                 ox+max(x for x,y in corners)*scale,oy+(height-min(y for x,y in corners))*scale)
            if not all(math.isfinite(v) for v in box):return None
            characters.extend(text);boxes.extend([box]*len(text))
    if ''.join(characters)!=reference:return None
    slide=prs.slides[number-1]
    if normalized(''.join(shape_text(slide.shapes)))!=reference:return None
    targets=[];cursor=0
    for index,shape in enumerate(slide.shapes):
        if not shape.has_text_frame:continue
        text=normalized(shape.text)
        if not text:continue
        if reference[cursor:cursor+len(text)]!=text:return None
        selected=boxes[cursor:cursor+len(text)];cursor+=len(text)
        box=(min(b[0] for b in selected),min(b[1] for b in selected),max(b[2] for b in selected),max(b[3] for b in selected))
        if box[0]>=box[2] or box[1]>=box[3]:return None
        targets.append({'shape':index,'bbox':box})
    return targets if cursor==len(reference) and targets else None


def measure(prs,rendered,targets):
    results={}
    with pdfium.PdfDocument(rendered) as doc:
        for number,rows in targets.items():
            slide=prs.slides[number-1]
            with closing(doc[number-1]) as page,closing(page.get_textpage()) as tp:
                found=observed_boxes(page,slide,rows);chars=[]
                for i in range(tp.count_chars()):
                    code=pdfium.raw.FPDFText_GetUnicode(tp,i)
                    if code==2 and pdfium.raw.FPDFText_IsHyphen(tp,i)==1:code=ord('-')
                    if code:chars.append(chr(code))
                complete=Counter(normalized(''.join(chars)))==Counter(normalized(''.join(shape_text(slide.shapes))))
            errors={t['shape']:max(abs(a-b) for a,b in zip(t['bbox'],found[t['shape']])) if t['shape'] in found else None for t in rows}
            results[number]=(found,errors,complete)
    return results


def passed(result):
    _,errors,complete=result
    return complete and all(v is not None and v<=2 for v in errors.values())


def finalize_words(source,target,report,settings):
    eligible=[p for p in report.get('pages',[]) if p.get('text_granularity')=='word']
    if not eligible:return
    prs=Presentation(target);targets={}
    with pdfium.PdfDocument(source) as doc:
        for item in eligible:
            with closing(doc[item['page']-1]) as page:rows=source_targets(prs,item['page'],page)
            if rows:targets[item['page']]=rows
    if not targets:raise ConversionError('final_word_provenance_unresolved')
    with tempfile.TemporaryDirectory(prefix='smartppt-final-words-',dir=Path(source).parent) as tmp:
        folder=Path(tmp);before=folder/'before.pptx';shutil.copyfile(target,before)
        # A restored neighboring slide can change Office's font import context.
        # Measure the actual full package, not the earlier all-word candidate.
        baseline=render_presentations([before],folder,settings)[0]
        measured=original=measure(prs,baseline,targets);rendered=baseline;changed=set();iterations=0
        for iteration in range(2):
            updated=False
            for number,rows in targets.items():
                found,errors,complete=measured[number]
                if not complete:continue
                for row in rows:
                    index=row['shape'];error=errors[index];shape=prs.slides[number-1].shapes[index]
                    if error is None or error<=2 or len(shape.text_frame.paragraphs)!=1 or len(shape.text_frame.paragraphs[0].runs)!=1:continue
                    if fit_shape(shape,row['bbox'],found[index]):updated=True;changed.add(number)
            if not updated:break
            candidate=folder/f'candidate-{iteration}.pptx';prs.save(candidate)
            rendered=render_presentations([candidate],folder,settings)[0]
            measured=measure(prs,rendered,targets);iterations+=1
        accepted=bool(changed) and all(passed(r) for r in measured.values())
        if accepted:
            accepted=all(accept_candidate(metric(source,baseline,n),metric(source,rendered,n)) for n in range(len(prs.slides)))
        if accepted:
            # Copy the exact package that was measured. Do not compose another
            # mixture after its final render and assume its geometry survived.
            candidate.replace(target)
        elif changed:measured=original
        for item in eligible:
            number=item['page'];result=measured.get(number)
            valid=result is not None and passed(result)
            errors=result[1] if result is not None else {}
            item['final_word_geometry']={'accepted':valid,'source_bound_shapes':len(errors),
                'position_passed':sum(v is not None and v<=2 for v in errors.values()),
                'position_tolerance_points':2,'calibration_passes':iterations if accepted else 0,
                'maximum_edge_error_points':max((v for v in errors.values() if v is not None),default=None),
                'full_package_rendered':True}
            if not valid:item.setdefault('warnings',[]).append('final_text_positions_require_review')


def try_finalize_words(source,target,report,settings):
    pending=deepcopy(report)
    try:finalize_words(source,target,pending,settings)
    except ConversionError as error:
        report['final_word_geometry_error']=error.code
        for item in report.get('pages',[]):
            if item.get('text_granularity')=='word':
                item['final_word_geometry']={'accepted':False,'error':error.code,'full_package_rendered':False}
                item.setdefault('warnings',[]).append('final_text_positions_require_review')
        return report
    report.clear();report.update(pending)
    return report
