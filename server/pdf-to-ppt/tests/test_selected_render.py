from contextlib import closing
from pathlib import Path
import os
import pypdfium2 as pdfium
from pptx import Presentation
from pptx.util import Pt
from reportlab.pdfgen import canvas
import pytest
from smartppt.config import Settings,ConversionError
from smartppt.layout import add_text,add_background,page_background
from smartppt.pdf import render_page
from smartppt.render_gate import render_presentations
from smartppt.selected_render import render_selected,SelectedRender,location,page_image


def deck(path,count=5):
    prs=Presentation();prs.slide_width=Pt(400);prs.slide_height=Pt(300)
    for i in range(count):
        slide=prs.slides.add_slide(prs.slide_layouts[6])
        add_text(slide,f'Page {i+1} Revenue {i+1}234.56',30,40,340,35,20,'Arial',False,(20,30+i*20,90))
    prs.save(path);return prs


@pytest.mark.parametrize('pages',[[],[0],[-1],[2,1],[1,1],[True],[1.0],[6]])
def test_invalid_selection_is_rejected_before_renderer(tmp_path,pages,monkeypatch):
    path=tmp_path/'input.pptx';deck(path);renderer=tmp_path/'renderer';renderer.touch()
    monkeypatch.setattr('smartppt.render_gate.subprocess.run',lambda *_a,**_k:pytest.fail('must not execute renderer'))
    with pytest.raises(ConversionError,match='invalid_render_page_selection'):
        render_presentations([path],tmp_path,Settings(renderer_path=str(renderer)),page_numbers=pages)


def test_wrong_export_count_cannot_be_used_as_a_sparse_result(tmp_path,monkeypatch):
    path=tmp_path/'input.pptx';deck(path);renderer=tmp_path/'renderer';renderer.touch()
    def ignores_range(*_a,**_k):
        c=canvas.Canvas(str(tmp_path/'input.pdf'))
        for i in range(5):c.drawString(30,30,str(i));c.showPage()
        c.save()
    monkeypatch.setattr('smartppt.render_gate.subprocess.run',ignores_range)
    with pytest.raises(ConversionError,match='layout_render_page_selection_failed'):
        render_selected([path],tmp_path,Settings(renderer_path=str(renderer)),(2,5))


def test_unrendered_page_has_no_implicit_blank_placeholder():
    render=SelectedRender(Path('subset.pdf'),(2,5,9))
    assert location(render,5)==(Path('subset.pdf'),1)
    assert location(Path('full.pdf'),5)==(Path('full.pdf'),4)
    with pytest.raises(ConversionError,match='unrendered_page_requested'):location(render,3)


@pytest.mark.parametrize('dynamic_field',[False,True])
def test_temporary_deck_trimming_preserves_source_and_contextual_fields(tmp_path,monkeypatch,dynamic_field):
    from pptx.oxml.xmlchemy import OxmlElement
    path=tmp_path/'original.pptx';prs=deck(path)
    if dynamic_field:
        field=OxmlElement('a:fld');field.set('id','{00000000-0000-0000-0000-000000000123}');field.set('type','slidenum')
        text=OxmlElement('a:t');text.text='1';field.append(text);prs.slides[0].shapes[0].text_frame.paragraphs[0]._p.append(field);prs.save(path)
    original=path.read_bytes();expected=[prs.slides[i]._element.xml for i in (1,4)];calls=[]
    def render(files,folder,settings,*,page_numbers):
        calls.append((files,page_numbers));actual=Presentation(files[0])
        if dynamic_field:assert files==[path] and len(actual.slides)==5 and page_numbers==(2,5)
        else:assert len(actual.slides)==2 and page_numbers==(1,2) and [s._element.xml for s in actual.slides]==expected
        return [tmp_path/'original.pdf']
    monkeypatch.setattr('smartppt.selected_render.render_presentations',render)
    result=render_selected([path],tmp_path,Settings(),(2,5))
    assert len(calls)==1 and result[0].pages==(2,5)
    assert path.read_bytes()==original


@pytest.mark.skipif(not os.getenv('SMARTPPT_TEST_RENDERER'),reason='real Office renderer required')
def test_nonconsecutive_and_hidden_pages_match_full_render_pixels_and_text(tmp_path):
    path=tmp_path/'full.pptx';prs=deck(path);settings=Settings(renderer_path=os.environ['SMARTPPT_TEST_RENDERER'])
    full=render_presentations([path],tmp_path,settings)[0]
    prs.slides[2]._element.set('show','0');partial=tmp_path/'partial.pptx';prs.save(partial)
    selected=render_selected([partial],tmp_path,settings,(2,3,5))[0]
    with pdfium.PdfDocument(full) as a,pdfium.PdfDocument(selected.path) as b:
        assert len(a)==5 and len(b)==3
        for index,number in enumerate(selected.pages):
            with closing(a[number-1]) as ap,closing(b[index]) as bp,closing(ap.get_textpage()) as at,closing(bp.get_textpage()) as bt:
                assert at.get_text_range()==bt.get_text_range()
                assert [at.get_charbox(i) for i in range(at.count_chars())]==[bt.get_charbox(i) for i in range(bt.count_chars())]
            assert render_page(full,number-1,max_side=1000).tobytes()==page_image(selected,number,max_side=1000).tobytes()


@pytest.mark.skipif(not os.getenv('SMARTPPT_TEST_RENDERER'),reason='real Office renderer required')
def test_sparse_regional_recovery_matches_full_and_keeps_untouched_slides(tmp_path,monkeypatch):
    from smartppt import regional
    source=tmp_path/'source.pdf';c=canvas.Canvas(str(source),pagesize=(400,300))
    for i in range(9):c.setFont('Helvetica',14);c.drawString(30,220,f'Region {i+1} value 123.45');c.showPage()
    c.save();prs=Presentation();prs.slide_width=Pt(400);prs.slide_height=Pt(300)
    with pdfium.PdfDocument(source) as doc:
        for i in range(9):
            with closing(doc[i]) as page:add_background(prs.slides.add_slide(prs.slide_layouts[6]),page_background(page,[],max_side=2200,scale_limit=2),400,300)
    before=[s._element.xml for s in prs.slides];a=tmp_path/'sparse.pptx';b=tmp_path/'ordinary.pptx';prs.save(a);prs.save(b);settings=Settings(renderer_path=os.environ['SMARTPPT_TEST_RENDERER'])
    selected=regional._recover_regions(source,a,[2,8],settings,word_regions=True)
    assert set(selected)=={2,8}
    with monkeypatch.context() as m:
        m.setattr(regional,'render_selected',lambda files,folder,settings,pages:render_presentations(files,folder,settings))
        ordinary=regional._recover_regions(source,b,[2,8],settings,word_regions=True)
    assert selected==ordinary
    after=Presentation(a)
    assert all(after.slides[i]._element.xml==before[i] for i in range(9) if i not in (1,7))
    ap,bp=render_presentations([a,b],tmp_path,settings)
    for i in range(9):assert render_page(ap,i,max_side=800).tobytes()==render_page(bp,i,max_side=800).tobytes()
