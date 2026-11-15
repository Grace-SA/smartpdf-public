"""Make the bundled CJK font and mixed-script advances travel with the PPT.

LibreOffice and PowerPoint differ in automatic Asian/Latin spacing. Isolate
script segments at verified rendered coordinates instead of relying on those
application defaults. This does not infer new text or claim font identity.
"""
from contextlib import closing
from copy import deepcopy
from pathlib import Path
import shutil
import re
import tempfile
import unicodedata
import math
import pypdfium2 as pdfium
from pptx import Presentation
from pptx.util import Pt
from .config import ConversionError
from .font_embedding import bundled_payloads,embed_noto,PORTABLE_FAMILIES,STYLES
FAMILIES=PORTABLE_FAMILIES
from .ocr_fit import observed_boxes,fit_shape,fit_local,local_box
from .quality import normalized,shape_text
from .render_gate import render_presentations,metric,accept_candidate


def script_segments(text):
    parts=[]
    for char in text:
        wide=unicodedata.east_asian_width(char) in ('W','F')
        if char.isspace() and parts:parts[-1][1]+=char
        elif parts and parts[-1][0]==wide:parts[-1][1]+=char
        else:parts.append([wide,char])
    return [s for _,s in parts] if any(k for k,_ in parts) and any(not k and s.strip() for k,s in parts) else [text]


def font_shapes(prs):
    frames=[]
    for i,slide in enumerate(prs.slides):
        for shape in slide.shapes:
            objects=([shape] if shape.has_text_frame else [])+(
                [cell for row in shape.table.rows for cell in row.cells if not cell.is_spanned] if shape.has_table else [])
            frames.extend((i,s) for s in objects if
                          any(r.font.name in FAMILIES for p in s.text_frame.paragraphs for r in p.runs))
    return frames


def split_script_shapes(prs,rendered,small_text_pages=()):
    targets={}
    with pdfium.PdfDocument(rendered) as doc:
        for index,slide in enumerate(prs.slides):
            selected=[];used=set()
            with closing(doc[index]) as page,closing(page.get_textpage()) as tp:
                text='';boxes=[];height=page.get_height()
                for i in range(tp.count_chars()):
                    code=pdfium.raw.FPDFText_GetUnicode(tp,i)
                    if not code:continue
                    for char in normalized(chr(code)):text+=char;boxes.append(tp.get_charbox(i))
                def bounds(bs):return (min(b[0] for b in bs),height-max(b[3] for b in bs),max(b[2] for b in bs),height-min(b[1] for b in bs))
                for shape in list(slide.shapes):
                    if not shape.has_text_frame or len(shape.text_frame.paragraphs)!=1:continue
                    if min(abs(shape.rotation-k) for k in (0,90,180,270,360))>8:continue
                    runs=shape.text_frame.paragraphs[0].runs
                    if len(runs)!=1 or runs[0].font.size is None:continue
                    if runs[0].font.name in ('Noto Sans SC','Noto Serif SC','SmartPDF Sans100','SmartPDF Serif200'):
                        chunks=script_segments(shape.text);kind='mixed-script'
                        if runs[0].font.name in ('SmartPDF Sans100','SmartPDF Serif200') and len(chunks)==1 and len(shape.text.split())>1:
                            chunks=re.findall(r'\s*\S+\s*',shape.text);kind='font-words'
                    elif index in small_text_pages and runs[0].font.size.pt<12 and runs[0].font.name in ('Arial','Times New Roman','Courier New'):
                        chunks=re.findall(r'\s*\S+\s*',shape.text);kind='small-words'
                    else:continue
                    needle=normalized(shape.text)
                    if len(chunks)<2 or len(chunks)>200 or not needle:continue
                    char_indices=None
                    if shape.rotation:
                        cx=(shape.left+shape.width/2)/12700;cy=(shape.top+shape.height/2)/12700
                        located=[]
                        for j,b in enumerate(boxes):
                            if j in used:continue
                            local=local_box(bounds([b]),cx,cy,shape.rotation)
                            x,y=(local[0]+local[2])/2,(local[1]+local[3])/2
                            if shape.left/12700-2<=x<=(shape.left+shape.width)/12700+2 and shape.top/12700-2<=y<=(shape.top+shape.height)/12700+2:
                                located.append((x,j))
                        located.sort()
                        if ''.join(text[j] for _,j in located)!=needle:continue
                        char_indices=[j for _,j in located]
                    matches=[];start=0
                    while (start:=text.find(needle,start))>=0:
                        end=start+len(needle);box=bounds(boxes[start:end])
                        distance=abs(box[0]-shape.left/12700)+abs(box[1]-shape.top/12700)
                        if not used.intersection(range(start,end)):matches.append((distance,start,end))
                        start+=1
                    if char_indices is None:
                        if not matches:continue
                        distance,start,end=min(matches)
                        if distance>max(24,runs[0].font.size.pt*4):continue
                        char_indices=list(range(start,end))
                    used.update(char_indices);cursor=0
                    for chunk in chunks:
                        length=len(normalized(chunk))
                        if not length:continue
                        desired=bounds([boxes[j] for j in char_indices[cursor:cursor+length]]);cursor+=length
                        element=deepcopy(shape._element);nonvisual=element.find('.//{http://schemas.openxmlformats.org/presentationml/2006/main}cNvPr')
                        ident=slide.shapes._next_shape_id;nonvisual.set('id',str(ident));nonvisual.set('name',f'Positioned text {ident}')
                        shape._element.addprevious(element)
                        new=next(s for s in slide.shapes if s._element is element)
                        new.text_frame.paragraphs[0].runs[0].text=chunk
                        if shape.rotation:
                            local=local_box(desired,cx,cy,shape.rotation)
                            width=local[2]-local[0]+runs[0].font.size.pt;box_height=new.height/12700
                            nx=local[0]+width/2;ny=shape.top/12700+box_height/2
                            c,s=math.cos(math.radians(shape.rotation)),math.sin(math.radians(shape.rotation))
                            x=cx+(nx-cx)*c-(ny-cy)*s;y=cy+(nx-cx)*s+(ny-cy)*c
                            new.left=Pt(x-width/2);new.top=Pt(y-box_height/2);new.width=Pt(width)
                        else:new.left=Pt(desired[0]);new.width=Pt(desired[2]-desired[0]+runs[0].font.size.pt)
                        selected.append((element,desired,kind))
                    shape._element.getparent().remove(shape._element)
            if selected:
                indices={id(s._element):i for i,s in enumerate(slide.shapes)}
                targets[index]=[{'shape':indices[id(e)],'bbox':box,'kind':kind} for e,box,kind in selected]
    return targets


def finalize_portable_fonts(source,target,report,settings):
    if report.get('font_portability',{}).get('validated'):return report
    prs=Presentation(target);font_runs=font_shapes(prs)
    scans={p['page']-1 for p in report.get('pages',[]) if p.get('route')=='paddle-ocr'}
    small_pages={i for i in scans for s in prs.slides[i].shapes if s.has_text_frame and not s.rotation and
                 len(s.text.split())>1 and any(r.font.size is not None and r.font.size.pt<12 and
                 r.font.name in ('Arial','Times New Roman','Courier New') for p in s.text_frame.paragraphs for r in p.runs)}
    if not font_runs and not small_pages:return report
    families=sorted({r.font.name for _,s in font_runs for p in s.text_frame.paragraphs for r in p.runs if r.font.name in FAMILIES})
    payloads={}
    for family in families:
        bold=any(r.font.bold for _,s in font_runs for p in s.text_frame.paragraphs for r in p.runs if r.font.name==family)
        styles={('boldItalic' if r.font.bold else 'italic') if r.font.italic else ('bold' if r.font.bold else 'regular')
                for _,s in font_runs for p in s.text_frame.paragraphs for r in p.runs if r.font.name==family}
        payloads[family]=bundled_payloads(bold,family,styles)
    font_pages={i for i,_ in font_runs}|small_pages
    with tempfile.TemporaryDirectory(prefix='smartppt-portable-font-',dir=Path(source).parent) as tmp:
        folder=Path(tmp);before=folder/'before.pptx';embedded=folder/'embedded.pptx';shutil.copyfile(target,before)
        shutil.copyfile(before,embedded)
        for family,faces in payloads.items():
            stage=folder/'font-stage.pptx';embed_noto(embedded,stage,faces,family);stage.replace(embedded)
        baseline=render_presentations([before],folder,settings)[0]
        prs=Presentation(embedded);fallback=Presentation(embedded);targets=split_script_shapes(prs,baseline,small_pages)
        candidate=folder/'candidate.pptx';prs.save(candidate)
        rendered=render_presentations([candidate],folder,settings)[0]
        with pdfium.PdfDocument(rendered) as doc:
            for index,rows in targets.items():
                with closing(doc[index]) as page:observed=observed_boxes(page,prs.slides[index],rows)
                for row in rows:
                    if row['shape'] in observed:
                        shape=prs.slides[index].shapes[row['shape']]
                        if shape.rotation in (0,90,180,270):fit_shape(shape,row['bbox'],observed[row['shape']])
                        else:
                            cx=(shape.left+shape.width/2)/12700;cy=(shape.top+shape.height/2)/12700
                            fit_local(shape,local_box(row['bbox'],cx,cy,shape.rotation),local_box(observed[row['shape']],cx,cy,shape.rotation))
        fitted=folder/'fitted.pptx';prs.save(fitted);rendered=render_presentations([fitted],folder,settings)[0]
        restored=[]
        with pdfium.PdfDocument(rendered) as doc:
            for index,rows in targets.items():
                with closing(doc[index]) as page:observed=observed_boxes(page,prs.slides[index],rows)
                accurate=all(row['shape'] in observed and max(abs(a-b) for a,b in zip(row['bbox'],observed[row['shape']]))<=2 for row in rows)
                if accurate and accept_candidate(metric(source,baseline,index),metric(source,rendered,index)):continue
                slide=prs.slides[index]
                for shape in list(slide.shapes):shape._element.getparent().remove(shape._element)
                for shape in fallback.slides[index].shapes:slide.shapes._spTree.insert_element_before(deepcopy(shape._element),'p:extLst')
                restored.append(index)
        if restored:
            prs.save(fitted);rendered=render_presentations([fitted],folder,settings)[0]
        original=Presentation(before)
        if any(normalized(''.join(shape_text(a.shapes)))!=normalized(''.join(shape_text(b.shapes))) for a,b in zip(original.slides,prs.slides)):
            raise ConversionError('portable_font_text_changed')
        scores={i:{'baseline':metric(source,baseline,i),'candidate':metric(source,rendered,i)} for i in font_pages}
        if not all(accept_candidate(s['baseline'],s['candidate']) for s in scores.values()):
            raise ConversionError('portable_font_visual_rejected')
        changed=set(targets)-set(restored)
        fitted.replace(target)
        for page in report.get('pages',[]):
            if page['page']-1 in changed and 'ink_targets' in page:
                page['ink_targets_before_font_portability']=page.pop('ink_targets')
        report['font_portability']={'embedded':bool(payloads),'validated':True,'family':families[0] if len(families)==1 else None,
            'families':{family:list(faces) for family,faces in payloads.items()},
            'faces':sorted({style for faces in payloads.values() for style in faces},key=STYLES.index),
            'whole_font':bool(payloads),'positioned_script_pages':[i+1 for i in sorted(changed) if any(r['kind']=='mixed-script' for r in targets[i])],
            'positioned_font_word_pages':[i+1 for i in sorted(changed) if any(r['kind']=='font-words' for r in targets[i])],
            'positioned_small_text_pages':[i+1 for i in sorted(changed) if any(r['kind']=='small-words' for r in targets[i])],
            'script_layout_rejected_pages':[i+1 for i in restored],
            'render_scores':{str(i+1):s for i,s in scores.items()},
            'validation':'font package, unchanged text, segment coordinates and independent LibreOffice render; client behavior can differ'}
    return report


def try_portable_fonts(source,target,report,settings):
    pending=deepcopy(report)
    try:finalize_portable_fonts(source,target,pending,settings)
    except ConversionError as error:
        report['font_portability']={'embedded':False,'error':error.code}
    else:report.clear();report.update(pending)
    from .final_words import try_finalize_words
    return try_finalize_words(source,target,report,settings)
