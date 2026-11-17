from hashlib import sha256
from types import SimpleNamespace
from pptx import Presentation
from reportlab.pdfgen import canvas
from smartppt.config import ConversionError
from smartppt.layout import add_text
from smartppt.native_words import refine_sparse_shapes,refine_sparse_words


def word_slide(count=2):
    prs=Presentation();slide=prs.slides.add_slide(prs.slide_layouts[6])
    add_text(slide,'placeholder',0,0,1,1,1);targets=[]
    for i in range(count):
        add_text(slide,f'Word{i}',20,20+i*25,80,20,12)
        targets.append({'shape':i+1,'bbox':(20,20+i*25,80,30+i*25)})
    observed={t['shape']:(t['bbox'][0]+3,t['bbox'][1],t['bbox'][2]+3,t['bbox'][3]) for t in targets}
    return prs,slide,targets,observed


def test_sparse_residual_moves_text_without_changing_letters_or_ids():
    _,slide,targets,observed=word_slide();before=[(s.shape_id,s.text,s.top,s.left) for s in slide.shapes]
    assert refine_sparse_shapes(slide,targets,observed)==2
    for original,shape in zip(before[1:],list(slide.shapes)[1:]):
        assert (shape.shape_id,shape.text,shape.top)==original[:3]
        assert abs((shape.left-original[3])/12700+3)<.001


def test_missing_or_unbounded_match_keeps_every_original_word():
    _,slide,targets,observed=word_slide();before=slide._element.xml
    del observed[2];assert refine_sparse_shapes(slide,targets,observed)==0
    assert slide._element.xml==before
    observed[2]=(23,45,83,65)  # A height ratio of 0.5 is not a small residual.
    assert refine_sparse_shapes(slide,targets,observed)==0 and slide._element.xml==before


def test_many_incorrect_words_do_not_trigger_a_sparse_retry():
    _,slide,targets,observed=word_slide(4);before=slide._element.xml
    assert refine_sparse_shapes(slide,targets,observed)==0 and slide._element.xml==before
    exact={t['shape']:t['bbox'] for t in targets}
    assert refine_sparse_shapes(slide,targets,exact)==0 and slide._element.xml==before


def residual_case(tmp_path,monkeypatch):
    import smartppt.ocr_fit as fit
    prs,slide,_,_=word_slide(1);path=tmp_path/'verified.pptx';prs.save(path)
    rendered=tmp_path/'observed.pdf';pdf=canvas.Canvas(str(rendered));pdf.showPage();pdf.save()
    pages={1:SimpleNamespace(get_size=lambda:(720,540))}
    parts={1:([(None,[{'text':'Word0','index':0,'box':(20,510,80,520)}])],[])}
    monkeypatch.setattr(fit,'observed_boxes',lambda page,slide,targets:{t['shape']:(t['bbox'][0]+3,t['bbox'][1],t['bbox'][2]+3,t['bbox'][3]) for t in targets})
    return prs,path,pages,parts,rendered


def test_optional_renderer_failure_preserves_verified_candidate(tmp_path,monkeypatch,settings):
    import smartppt.native_words as words
    prs,path,pages,parts,rendered=residual_case(tmp_path,monkeypatch);before=sha256(path.read_bytes()).hexdigest();xml=prs.slides[0]._element.xml
    def fail(*args,**kwargs):raise ConversionError('layout_render_failed')
    monkeypatch.setattr(words,'render_selected',fail)
    result,new_path,renders,evidence=refine_sparse_words(path,prs,pages,parts,rendered,tmp_path,settings)
    assert result is prs and new_path==path and renders=={1:rendered} and not evidence
    assert prs.slides[0]._element.xml==xml and sha256(path.read_bytes()).hexdigest()==before


def test_residual_retry_is_bounded_to_two_measured_passes(tmp_path,monkeypatch,settings):
    import smartppt.native_words as words
    from smartppt.selected_render import SelectedRender
    prs,path,pages,parts,rendered=residual_case(tmp_path,monkeypatch);calls=[]
    def render(files,folder,settings,selection):
        calls.append(selection);return [SelectedRender(rendered,selection)]
    monkeypatch.setattr(words,'render_selected',render)
    _,new_path,_,evidence=refine_sparse_words(path,prs,pages,parts,rendered,tmp_path,settings)
    assert calls==[(1,),(1,)] and evidence=={1:{'passes':2,'word_adjustments':2}}
    assert new_path!=path  # Final source/pixel/position gates still decide acceptance.
