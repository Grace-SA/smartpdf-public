from copy import deepcopy
from pptx import Presentation
from smartppt.layout import convert_native
from smartppt.pdf import inspect_pdf
from smartppt.content_gate import enforce_content_safety


def test_known_content_loss_is_visible_fallback_with_retained_evidence(pdf_file,tmp_path):
    target=tmp_path/'result.pptx';pages=convert_native(pdf_file,target)
    prs=Presentation(target)
    text=next(s for s in prs.slides[0].shapes if s.has_text_frame)
    text.text='WRONG NUMBER 987654321';prs.save(target)
    report=enforce_content_safety(pdf_file,target,inspect_pdf(pdf_file),{'pages':[{'page':i+1,**p} for i,p in enumerate(pages)]})
    assert report['source_image_pages']==[1]
    page=report['pages'][0];assert page['route']=='source-image-fallback'
    assert 'numeric_mismatch' in page['content_gate']['triggered_by']
    assert page['content_gate']['before']['character_recall']<1
    result=Presentation(target)
    assert len(result.slides[0].shapes)==1 and result.slides[0].shapes[0].shape_type==13
    assert any(s.has_text_frame for s in result.slides[1].shapes)


def test_hidden_ocr_layer_never_overrules_scan_consensus(pdf_file,tmp_path):
    target=tmp_path/'result.pptx';pages=convert_native(pdf_file,target)
    prs=Presentation(target);next(s for s in prs.slides[0].shapes if s.has_text_frame).text='OCR differs';prs.save(target)
    report={'pages':[{'page':i+1,**p} for i,p in enumerate(pages)]};report['pages'][0]['route']='paddle-ocr'
    enforce_content_safety(pdf_file,target,inspect_pdf(pdf_file),report)
    assert report['source_image_pages']==[]
    assert any(s.has_text_frame and s.text=='OCR differs' for s in Presentation(target).slides[0].shapes)
