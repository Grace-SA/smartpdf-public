"""Explicit single-line text metrics, independent of inherited theme defaults."""
from copy import deepcopy
from pptx.util import Pt,Length
from pptx.oxml.ns import qn

def explicit_line_metrics(shape):
    if len(shape.text_frame.paragraphs)!=1:return False
    paragraph=shape.text_frame.paragraphs[0];props=paragraph._p.pPr
    return (props is not None and props.get('fontAlgn')=='base' and
            props.find(qn('a:defRPr')) is not None and paragraph._p.find(qn('a:endParaRPr')) is not None
            and isinstance(paragraph.line_spacing,Length))

def set_line_metrics(shape):
    paragraph=shape.text_frame.paragraphs[0]
    if len(shape.text_frame.paragraphs)!=1 or len(paragraph.runs)!=1:return
    run=paragraph.runs[0]
    if run.font.size is None:return
    props=paragraph._p.get_or_add_pPr();props.set('fontAlgn','base')
    for parent,tag in [(props,'a:defRPr'),(paragraph._p,'a:endParaRPr')]:
        old=parent.find(qn(tag))
        if old is not None:parent.remove(old)
        element=deepcopy(run._r.get_or_add_rPr());element.tag=qn(tag);parent.append(element)
    paragraph.line_spacing=Pt(run.font.size.pt)
