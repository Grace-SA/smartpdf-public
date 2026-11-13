"""Return unverified OCR lines to their exact source pixels after Office fitting."""
from contextlib import closing
from copy import deepcopy
from io import BytesIO
from pathlib import Path
import tempfile
from PIL import Image
import pypdfium2 as pdfium
from pptx import Presentation
from .consensus import erase_bounds
from .ocr_fit import observed_boxes,raster_bounds
from .render_gate import render_presentations
from .config import ConversionError


def restore_lines(slide,item,indices,image_path,record):
    targets=item['ink_targets'];source_indices=item['ocr_line_indices']
    if len(targets)!=len(source_indices):raise ConversionError('invalid_ocr_geometry_provenance')
    background=slide.shapes[0]
    with Image.open(BytesIO(background.image.blob)) as im:raster=im.convert('RGB').copy()
    with Image.open(image_path) as im:original=im.convert('RGB').copy()
    if raster.size!=original.size:raise ConversionError('ocr_geometry_mismatch')
    selected=[];removed=[]
    for target,line_index in zip(targets,source_indices):
        shape=slide.shapes[target['shape']]
        if target['shape'] in indices:
            l,t,r,b=target.get('erase_box',erase_bounds(record['lines'][line_index]));l=max(0,l);t=max(0,t);r=min(r,original.width);b=min(b,original.height)
            raster.paste(original.crop((l,t,r,b)),(l,t));removed.append((shape,line_index))
        else:selected.append((shape,target,line_index))
    # Text boxes have no image relationships. Preserve the existing background
    # transform exactly, including quarter-turn page orientation.
    stream=BytesIO();raster.save(stream,format='PNG');stream.seek(0)
    picture=slide.shapes.add_picture(stream,background.left,background.top,width=background.width,height=background.height)
    picture._element.spPr.replace(picture._element.spPr.xfrm,deepcopy(background._element.spPr.xfrm))
    parent=background._element.getparent();parent.remove(picture._element);parent.replace(background._element,picture._element)
    for shape,_ in removed:shape._element.getparent().remove(shape._element)
    updated=[]
    for shape,target,line_index in selected:
        position=next(i for i,s in enumerate(slide.shapes) if s._element is shape._element)
        updated.append({**target,'shape':position})
    item['ink_targets']=updated;item['ocr_line_indices']=[line_index for _,_,line_index in selected]
    item['editable_lines']=len(selected)
    item.setdefault('geometry_rejected_line_indices',[]).extend(i for _,i in removed)
    item['warnings']=sorted(set(item['warnings']+['ocr_position_unverified_kept_as_image','partial_ocr_editability']))


def verify_ocr_geometry(source,target,reports,images,records,settings):
    eligible=[p for p in reports if p['route']=='paddle-ocr' and p.get('ink_targets')]
    if not eligible:return
    with tempfile.TemporaryDirectory(prefix='smartppt-ocr-gate-',dir=Path(source).parent) as temp:
        folder=Path(temp);prs=Presentation(target)
        for iteration in range(3):
            candidate=folder/f'check-{iteration}.pptx';prs.save(candidate)
            rendered=render_presentations([candidate],folder,settings)[0];changed=False
            with pdfium.PdfDocument(rendered) as doc:
                for item in eligible:
                    index=item['page']-1;slide=prs.slides[index];targets=item['ink_targets']
                    if not targets:continue
                    with closing(doc[index]) as page:
                        observed=observed_boxes(page,slide,targets);ink=raster_bounds(page,slide,targets,observed)
                    errors={t['shape']:max(abs(a-b) for a,b in zip(*ink[t['shape']])) if t['shape'] in ink else None for t in targets}
                    rejected={i for i,e in errors.items() if e is None or e>2}
                    item['ocr_geometry_verification']={'tolerance_points':2,'matched_lines':len(observed),'verified_lines':len(targets)-len(rejected),'max_ink_error_points':max((e for e in errors.values() if e is not None),default=None),'iteration':iteration+1}
                    if rejected:
                        # If repeated restoration changes neighboring measurements,
                        # retain the original scan rather than claim convergence.
                        if iteration==2:rejected={t['shape'] for t in targets}
                        restore_lines(slide,item,rejected,images[index],records[index]);changed=True
            if not changed:break
        for item in eligible:
            if not item['ink_targets']:item['ocr_geometry_verification']={'tolerance_points':2,'verified_lines':0,'all_lines_restored':True}
        prs.save(target)
