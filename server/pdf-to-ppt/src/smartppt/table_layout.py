"""Retain source-bound native cells while repairing the surrounding text.

This is a bounded candidate for existing tables, not table detection. A grid
whose cell text cannot be bound exactly to source words is never guessed.
"""
from contextlib import closing
from copy import deepcopy
from statistics import median
from collections import Counter
from io import BytesIO
import math
import numpy as np
from PIL import Image
import pypdfium2 as pdfium
from pptx import Presentation
from pptx.enum.text import MSO_ANCHOR,PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.util import Pt
from .config import ConversionError
from .layout import font_family
from .quality import normalized,shape_text
from .ocr_fit import observed_boxes
from .regional import rendered_word_regions
from .selected_render import render_selected,location,page_metric
from .render_gate import accept_candidate


def word_targets(prs,page,parts):
    width,height=page.get_size();sw,sh=prs.slide_width/12700,prs.slide_height/12700
    scale=min(sw/width,sh/height);ox=(sw-width*scale)/2;oy=(sh-height*scale)/2
    result=[]
    for _,runs in parts:
        for run in runs:
            l,b,r,t=run['box']
            result.append({'shape':len(result)+1,'text':run['text'],'source_index':run['index'],
                           'bbox':(ox+l*scale,oy+(height-t)*scale,ox+r*scale,oy+(height-b)*scale)})
    return result


def bind_cells(slide,targets):
    tables=[shape for shape in slide.shapes if shape.has_table]
    if not tables or any(hasattr(s,'shapes') for s in slide.shapes):return None
    bindings=[];used=set()
    for shape in tables:
        if shape.rotation:return None
        table=shape.table;y=shape.top/12700
        for ri,row in enumerate(table.rows):
            x=shape.left/12700
            for ci,cell in enumerate(row.cells):
                if not cell.is_spanned:
                    width=sum(table.columns[j].width for j in range(ci,ci+cell.span_width))/12700
                    height=sum(table.rows[j].height for j in range(ri,ri+cell.span_height))/12700
                    words=[t for t in targets if x<=(t['bbox'][0]+t['bbox'][2])/2<x+width
                           and y<=(t['bbox'][1]+t['bbox'][3])/2<y+height]
                    if normalized(cell.text)!=normalized(''.join(t['text'] for t in words)):return None
                    indices={t['shape'] for t in words}
                    if indices&used:return None
                    if any(t['bbox'][0]<x-2 or t['bbox'][2]>x+width+2 or
                           t['bbox'][1]<y-2 or t['bbox'][3]>y+height+2 for t in words):return None
                    used|=indices;bindings.append((cell,words))
                x+=table.columns[ci].width/12700
            y+=row.height/12700
    return bindings,used


def table_decoration(picture,frame):
    """Prove flat cell interiors before replacing a raster grid with cells.

    Original exports often include transparent ruling and flat background PNGs
    beneath native tables. Photos, letters, gradients and uncertain crops stay
    unsupported; a later render gate still checks the native replacement.
    """
    if picture.rotation:return False
    if not (picture.left>=frame.left-Pt(1) and picture.top>=frame.top-Pt(1) and
            picture.left+picture.width<=frame.left+frame.width+Pt(1) and
            picture.top+picture.height<=frame.top+frame.height+Pt(1)):return False
    crops=(picture.crop_left,picture.crop_top,picture.crop_right,picture.crop_bottom)
    if any(not math.isfinite(v) or v<0 or v>=1 for v in crops) or crops[0]+crops[2]>=1 or crops[1]+crops[3]>=1:return False
    if picture.width<=0 or picture.height<=0:return False
    try:
        with Image.open(BytesIO(picture.image.blob)) as image:
            if image.width*image.height>16_000_000:return False
            sx=image.width*(1-crops[0]-crops[2])/picture.width
            sy=image.height*(1-crops[1]-crops[3])/picture.height
            def pixel_x(x):return (x-picture.left)*sx+image.width*crops[0]
            def pixel_y(y):return (y-picture.top)*sy+image.height*crops[1]
            y=frame.top;checked=0
            for ri,row in enumerate(frame.table.rows):
                x=frame.left
                for ci,cell in enumerate(row.cells):
                    if not cell.is_spanned:
                        width=sum(frame.table.columns[j].width for j in range(ci,ci+cell.span_width))
                        height=sum(frame.table.rows[j].height for j in range(ri,ri+cell.span_height))
                        box=(max(0,math.ceil(pixel_x(x+Pt(1)))),max(0,math.ceil(pixel_y(y+Pt(1)))),
                             min(image.width,math.floor(pixel_x(x+width-Pt(1)))),min(image.height,math.floor(pixel_y(y+height-Pt(1)))))
                        if box[2]>box[0] and box[3]>box[1]:
                            pixels=np.asarray(image.crop(box).convert('RGBA'),dtype=np.float32).copy()
                            # RGB bytes under zero alpha do not carry visible ink.
                            pixels[:,:,:3]*=pixels[:,:,3:4]/255
                            if np.ptp(pixels,axis=(0,1)).max()>4:return False
                            checked+=1
                    x+=frame.table.columns[ci].width
                y+=row.height
            return checked>0
    except (OSError,ValueError,Image.DecompressionBombError):return False


def portable_cell_insets(cell):
    """Keep uniform paragraph right padding when Office saves a native table.

    LibreOffice imports paragraph marR but drops it on PPTX export. A shared
    positive inset belongs equally to the cell; mixed paragraph insets cannot
    be moved without changing their relative widths and are left untouched.
    """
    paragraphs=list(cell.text_frame.paragraphs)
    margins=[int(p._p.pPr.get('marR','0')) if p._p.pPr is not None else 0 for p in paragraphs]
    if not margins or margins[0]<=0 or len(set(margins))!=1:return
    cell.margin_right+=margins[0]
    for paragraph in paragraphs:paragraph._p.get_or_add_pPr().set('marR','0')


def flat_background(picture):
    """Prove a retained picture carries only a uniform fill, never old letters.

    Some exporters put a blank bitmap behind a heading. Bounds overlap alone
    must not make that heading discard a separate, valid native table.
    """
    if picture.rotation or picture.width<=0 or picture.height<=0:return False
    crops=(picture.crop_left,picture.crop_top,picture.crop_right,picture.crop_bottom)
    if any(not math.isfinite(v) or v<0 or v>=1 for v in crops) or crops[0]+crops[2]>=1 or crops[1]+crops[3]>=1:return False
    try:
        with Image.open(BytesIO(picture.image.blob)) as image:
            if image.width*image.height>16_000_000:return False
            pixels=np.asarray(image.convert('RGBA'),dtype=np.uint16)
            alpha=pixels[:,:,3]
            if np.any(alpha!=alpha[0,0]):return False
            return bool(alpha[0,0]==0 or np.all(pixels[:,:,:3]==pixels[0,0,:3]))
    except (OSError,ValueError,Image.DecompressionBombError):return False


def build_hybrid(slide,original,targets):
    bound=bind_cells(original,targets)
    if bound is None:return None
    _,covered=bound
    if not covered:return None
    # A picture can already contain these letters. Superimposing native cells
    # may look correct until the user edits them and reveals the old raster.
    decorations=set();tables=[s for s in original.shapes if s.has_table]
    for shape in original.shapes:
        if shape.shape_type!=MSO_SHAPE_TYPE.PICTURE:
            if not shape.has_text_frame and not shape.has_table:
                # Standalone vector rules/charts are not part of the cell grid
                # and would remain after moving it, just like raster borders.
                box=(shape.left/12700-1,shape.top/12700-1,(shape.left+shape.width)/12700+1,(shape.top+shape.height)/12700+1)
                if shape.rotation or any(min(box[2],(t.left+t.width)/12700+1)>max(box[0],t.left/12700-1) and
                    min(box[3],(t.top+t.height)/12700+1)>max(box[1],t.top/12700-1) for t in tables):return None
            continue
        if shape.rotation:return None
        if any(table_decoration(shape,table) for table in tables):
            decorations.add(shape.shape_id);continue
        box=(shape.left/12700,shape.top/12700,(shape.left+shape.width)/12700,(shape.top+shape.height)/12700)
        # A thin raster border may miss every word box but still remain behind
        # when the table is moved. Do not retain uncertain table decorations.
        if any(min(box[2],(t.left+t.width)/12700+1)>max(box[0],t.left/12700-1) and
               min(box[3],(t.top+t.height)/12700+1)>max(box[1],t.top/12700-1) for t in tables):return None
        if any(min(box[2],t['bbox'][2]+2)>max(box[0],t['bbox'][0]-2) and
               min(box[3],t['bbox'][3]+2)>max(box[1],t['bbox'][1]-2) for t in targets) and not flat_background(shape):return None
    for shape in original.shapes:
        if shape.has_text_frame or shape.shape_id in decorations:continue
        for node in shape._element.iter():
            for key,value in node.attrib.items():
                if not key.startswith('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'):continue
                if value not in slide.part.rels or value not in original.part.rels:return None
                a,b=slide.part.rels[value],original.part.rels[value]
                if (a.reltype,a.target_ref,a.is_external)!=(b.reltype,b.target_ref,b.is_external):return None
    # Keep the actual grid, fills and graphics. Reusing the word-mode raster
    # would leave a second, immovable copy of the table underneath its cells.
    words=[(t['source_index'],deepcopy(slide.shapes[t['shape']]._element))
           for t in targets if t['shape'] not in covered]
    for shape in list(slide.shapes):shape._element.getparent().remove(shape._element)
    for shape in original.shapes:
        if not shape.has_text_frame and shape.shape_id not in decorations:
            slide.shapes._spTree.insert_element_before(deepcopy(shape._element),'p:extLst')
    for _,element in words:
        element.xpath('.//p:cNvPr')[0].set('id',str(slide.shapes._next_shape_id))
        slide.shapes._spTree.insert_element_before(element,'p:extLst')
    bound=bind_cells(slide,targets)
    if bound is None:return None
    bindings,_=bound
    ordered=list(words)
    for shape in list(slide.shapes):
        if not shape.has_table:continue
        cells={id(cell._tc) for row in shape.table.rows for cell in row.cells}
        indices=[t['source_index'] for cell,ts in bindings if id(cell._tc) in cells for t in ts]
        if not indices:return None
        ordered.append((min(indices),shape._element))
    # Header/footer occurrence order must survive hybrid composition too.
    for _,element in ordered:element.getparent().remove(element)
    for _,element in sorted(ordered,key=lambda pair:pair[0]):
        slide.shapes._spTree.insert_element_before(element,'p:extLst')
    for cell,_ in bindings:
        portable_cell_insets(cell)
        for node in cell._tc.iter():
            if node.tag.rsplit('}',1)[-1] not in ('latin','ea','cs'):continue
            name=node.get('typeface','')
            family,_=font_family(name,cell.text)
            # Only the explicitly configured, licensed CJK serif substitute.
            # Do not rewrite arbitrary theme, symbol or document fonts.
            if family=='Noto Serif SC':node.set('typeface',family)
    return bindings


def align_cells(bindings,observed):
    changed=False
    for cell,words in bindings:
        if not words or not all(t['shape'] in observed for t in words):continue
        deltas=[observed[t['shape']][k]-t['bbox'][k] for t in words for k in (1,3)]
        if not all(math.isfinite(v) for v in deltas):continue
        if max(deltas)-min(deltas)>1 or max(abs(v) for v in deltas)<=2:continue
        shift=median(deltas)
        # Bottom padding can increase a row's minimum height and move the grid.
        # First use top anchoring, then measure its actual glyphs again.
        if cell.vertical_anchor!=MSO_ANCHOR.TOP:
            cell.vertical_anchor=MSO_ANCHOR.TOP;cell.margin_top=0;changed=True
        elif cell.margin_top/12700>=shift:
            cell.margin_top-=Pt(shift);changed=True
    return changed


def align_cell_horizontal(cell,words,observed):
    """Move a measured single line within its cell, preserving its usable width."""
    if not words or not all(t['shape'] in observed for t in words):return False
    paragraphs=list(cell.text_frame.paragraphs)
    if len(paragraphs)!=1 or paragraphs[0].alignment!=PP_ALIGN.LEFT:return False
    for boxes in ([t['bbox'] for t in words],[observed[t['shape']] for t in words]):
        heights=[b[3]-b[1] for b in boxes]
        if min(heights)<=0 or min(b[3] for b in boxes)-max(b[1] for b in boxes)<min(heights)*.5:return False
    deltas=[observed[t['shape']][k]-t['bbox'][k] for t in words for k in (0,2)]
    if not all(math.isfinite(v) for v in deltas):return False
    error=max(abs(v) for v in deltas)
    # Keep headroom for Office's coordinate rounding on save/reopen.
    # The acceptance gate stays at 2pt; already well-centered cells stay put.
    if error<=1.5:return False
    # A translation must bring every word edge within the existing 2pt gate.
    shift=-(min(deltas)+max(deltas))/2
    if abs(shift)>2 or any(abs(v+shift)>2 for v in deltas):return False
    if error-max(abs(v+shift) for v in deltas)<.01:return False
    left=cell.margin_left+Pt(shift);right=cell.margin_right-Pt(shift)
    if min(left,right)<0:return False
    cell.margin_left=left;cell.margin_right=right
    return True


def restore_tables(word_file,original,source,pages,parts,baseline,settings,folder):
    """Return only fully measured table pages; never mutate the caller's file."""
    reference=Presentation(word_file);candidate=Presentation(word_file);bindings={};targets={}
    for number in sorted(parts):
        targets[number]=word_targets(reference,pages[number],parts[number])
        bound=build_hybrid(candidate.slides[number-1],original.slides[number-1],targets[number])
        if bound is not None:bindings[number]=bound
    if not bindings:return {},None
    selection=tuple(sorted(bindings));rendered=None
    for iteration in range(3):
        path=folder/f'table-layout-{iteration}.pptx';candidate.save(path)
        rendered=render_selected([path],folder,settings,selection)[0]
        if iteration==2:break
        changed=False
        for number,bound in bindings.items():
            output,index=location(rendered,number)
            with pdfium.PdfDocument(output) as doc,closing(doc[index]) as page:
                observed=observed_boxes(page,reference.slides[number-1],targets[number])
            changed=align_cells(bound,observed) or changed
            for cell,words in bound:changed=align_cell_horizontal(cell,words,observed) or changed
        if not changed:break
    accepted={}
    for number,bound in bindings.items():
        slide=candidate.slides[number-1]
        boxes=rendered_word_regions(reference,number,pages[number],parts[number],rendered)
        # Rendering alone cannot prove that editable text is complete. Check
        # package text too, independent of text hidden in pictures or clipping.
        actual=normalized(''.join(shape_text(slide.shapes)))
        expected=normalized(''.join(t['text'] for t in targets[number]))
        if actual!=expected or not all(boxes):continue
        output,index=location(rendered,number)
        with pdfium.PdfDocument(output) as doc,closing(doc[index]) as page,closing(page.get_textpage()) as textpage:
            characters=[]
            for i in range(textpage.count_chars()):
                code=pdfium.raw.FPDFText_GetUnicode(textpage,i)
                if code==2 and pdfium.raw.FPDFText_IsHyphen(textpage,i)==1:code=ord('-')
                if code:characters.append(chr(code))
        # Chart labels and other non-textbox objects can introduce a second
        # native copy, even when each required word can be matched correctly.
        if Counter(normalized(''.join(characters)))!=Counter(expected):continue
        old,new=page_metric(source,baseline,number),page_metric(source,rendered,number)
        if not accept_candidate(old,new):continue
        accepted[number]={'tables':sum(s.has_table for s in slide.shapes),'bound_cells':len(bound),
            'position_passed':len(targets[number]),'position_tolerance_points':2,
            'baseline':old,'candidate':new,'source_cell_indices':[
                [t['source_index'] for t in words] for _,words in bound]}
    return accepted,candidate


def try_restore_tables(*args,**kwargs):
    try:return restore_tables(*args,**kwargs)
    except ConversionError:return {},None
