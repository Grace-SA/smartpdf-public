"""Restore source occurrence order after disjoint regional text additions."""
from copy import deepcopy
from pathlib import Path
import shutil,tempfile
import numpy as np
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from .config import ConversionError
from .selected_render import render_selected,page_image


def restore_source_order(source,target,reports,settings):
    """Change only text stacking order, after an independent unchanged-pixel gate.

    The map retains each original recovery-stage slot for provenance verification.
    No text, coordinates, source indices or font properties are rewritten.
    """
    candidates={}
    for number,report in reports.items():
        indices=report.get('source_run_indices')
        if not indices:continue
        order=sorted(range(len(indices)),key=lambda i:(indices[i],i))
        if order!=list(range(len(indices))):candidates[number]=order
    if not candidates:return
    prs=Presentation(target);valid={}
    for number,order in candidates.items():
        slide=prs.slides[number-1];shapes=list(slide.shapes)
        if (len(shapes)!=len(order)+1 or shapes[0].shape_type!=MSO_SHAPE_TYPE.PICTURE
                or any(not s.has_text_frame for s in shapes[1:])):
            reports[number].setdefault('warnings',[]).append('source_reading_order_unverified');continue
        elements=[s._element for s in shapes[1:]]
        for element in elements:element.getparent().remove(element)
        for i in order:slide.shapes._spTree.insert_element_before(elements[i],'p:extLst')
        valid[number]=order
    if not valid:return
    with tempfile.TemporaryDirectory(prefix='smartppt-reading-order-',dir=Path(source).parent) as tmp:
        folder=Path(tmp);before=folder/'before.pptx';candidate=folder/'candidate.pptx'
        shutil.copyfile(target,before);prs.save(candidate)
        try:
            a,b=render_selected([before,candidate],folder,settings,tuple(sorted(valid)))
            accepted=[]
            for number in valid:
                old=page_image(a,number,max_side=1800);new=page_image(b,number,max_side=1800)
                if old.size==new.size and np.array_equal(np.asarray(old),np.asarray(new)):accepted.append(number)
        except ConversionError:
            for number in valid:reports[number].setdefault('warnings',[]).append('source_reading_order_render_unavailable')
            return
        final=Presentation(target)
        for number,order in valid.items():
            if number not in accepted:
                reports[number].setdefault('warnings',[]).append('source_reading_order_visual_change');continue
            slide=final.slides[number-1]
            for shape in list(slide.shapes)[1:]:shape._element.getparent().remove(shape._element)
            for shape in list(prs.slides[number-1].shapes)[1:]:slide.shapes._spTree.insert_element_before(deepcopy(shape._element),'p:extLst')
            mapping=[0]*len(order)
            for new_index,old_index in enumerate(order,1):mapping[old_index]=new_index
            reports[number]['source_shape_indices']=mapping
            reports[number]['source_reading_order_verified']=True
        if accepted:final.save(target)
