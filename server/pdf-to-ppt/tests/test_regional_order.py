from io import BytesIO
import os
from PIL import Image
from pptx import Presentation
from pptx.util import Pt
from reportlab.pdfgen import canvas
import pytest
from smartppt.config import Settings,ConversionError
from smartppt.layout import add_text
from smartppt.regional_order import restore_source_order
from smartppt.render_gate import render_presentations
from smartppt.pdf import render_page


def fixture(tmp_path):
    source=tmp_path/'source.pdf';c=canvas.Canvas(str(source),pagesize=(400,300));c.drawString(30,250,'First middle last');c.save()
    prs=Presentation();prs.slide_width=Pt(400);prs.slide_height=Pt(300);slide=prs.slides.add_slide(prs.slide_layouts[6])
    image=BytesIO();Image.new('RGB',(400,300),'white').save(image,format='PNG');image.seek(0)
    slide.shapes.add_picture(image,0,0,prs.slide_width,prs.slide_height)
    for text,x in [('First',30),('last',180),('middle',100)]:add_text(slide,text,x,40,75,30,16,'Arial')
    target=tmp_path/'target.pptx';prs.save(target)
    return source,target,{1:{'source_run_indices':[0,13,6],'editable_runs':3,'warnings':[]}}


def test_failed_order_render_leaves_original_bytes_and_no_verified_flag(tmp_path,monkeypatch):
    source,target,reports=fixture(tmp_path);before=target.read_bytes()
    def unavailable(*args):raise ConversionError('layout_render_failed')
    monkeypatch.setattr('smartppt.regional_order.render_selected',unavailable)
    restore_source_order(source,target,reports,Settings())
    assert target.read_bytes()==before and not reports[1].get('source_reading_order_verified')
    assert 'source_reading_order_render_unavailable' in reports[1]['warnings']


def test_changed_pixels_reject_reordering(tmp_path,monkeypatch):
    source,target,reports=fixture(tmp_path);before=target.read_bytes()
    monkeypatch.setattr('smartppt.regional_order.render_selected',lambda *_:('before','after'))
    monkeypatch.setattr('smartppt.regional_order.page_image',lambda p,*a,**k:Image.new('RGB',(10,10),'white' if p=='before' else 'black'))
    restore_source_order(source,target,reports,Settings())
    assert target.read_bytes()==before and reports[1]['warnings']==['source_reading_order_visual_change']


def test_already_ordered_report_never_renders(tmp_path,monkeypatch):
    source,target,reports=fixture(tmp_path);reports[1]['source_run_indices']=[0,6,13];before=target.read_bytes()
    monkeypatch.setattr('smartppt.regional_order.render_selected',lambda *_:pytest.fail('unnecessary render'))
    restore_source_order(source,target,reports,Settings());assert target.read_bytes()==before


@pytest.mark.skipif(not os.getenv('SMARTPPT_TEST_RENDERER'),reason='real Office renderer required')
def test_real_source_order_restored_without_changing_text_xml_or_pixels(tmp_path):
    source,target,reports=fixture(tmp_path);settings=Settings(renderer_path=os.environ['SMARTPPT_TEST_RENDERER'])
    before=Presentation(target);xml={s.text:s._element.xml for s in list(before.slides[0].shapes)[1:]}
    old=render_page(render_presentations([target],tmp_path,settings)[0],0,max_side=1800).tobytes()
    restore_source_order(source,target,reports,settings)
    after=Presentation(target);shapes=list(after.slides[0].shapes)[1:]
    assert [s.text for s in shapes]==['First','middle','last']
    assert all(s._element.xml==xml[s.text] for s in shapes)
    assert reports[1]['source_shape_indices']==[1,3,2] and reports[1]['source_reading_order_verified']
    rendered=render_presentations([target],tmp_path,settings)[0]
    assert render_page(rendered,0,max_side=1800).tobytes()==old
    import pypdfium2 as pdfium
    from contextlib import closing
    with pdfium.PdfDocument(rendered) as doc,closing(doc[0]) as page,closing(page.get_textpage()) as tp:
        text=tp.get_text_range();assert text.index('First')<text.index('middle')<text.index('last')


def test_one_failed_page_does_not_reorder_it_or_erase_accepted_page(tmp_path,monkeypatch):
    source,target,reports=fixture(tmp_path)
    from copy import deepcopy
    prs=Presentation(target);slide=prs.slides.add_slide(prs.slide_layouts[6])
    # Reuse the existing image relationship only by adding the image normally.
    picture=prs.slides[0].shapes[0];slide.shapes.add_picture(BytesIO(picture.image.blob),0,0,prs.slide_width,prs.slide_height)
    for shape in list(prs.slides[0].shapes)[1:]:slide.shapes._spTree.insert_element_before(deepcopy(shape._element),'p:extLst')
    prs.save(target);reports[2]=deepcopy(reports[1]);old=prs.slides[1]._element.xml
    monkeypatch.setattr('smartppt.regional_order.render_selected',lambda *_:('before','after'))
    monkeypatch.setattr('smartppt.regional_order.page_image',lambda p,n,**k:Image.new('RGB',(10,10),'black' if p=='after' and n==2 else 'white'))
    restore_source_order(source,target,reports,Settings());final=Presentation(target)
    assert [s.text for s in list(final.slides[0].shapes)[1:]]==['First','middle','last']
    assert final.slides[1]._element.xml==old
    assert reports[1]['source_reading_order_verified'] and 'source_shape_indices' not in reports[2]


def test_unexpected_slide_structure_is_left_unchanged(tmp_path,monkeypatch):
    source,target,reports=fixture(tmp_path);prs=Presentation(target)
    add_text(prs.slides[0],'unaccounted',250,40,100,30,16);prs.save(target);before=target.read_bytes()
    monkeypatch.setattr('smartppt.regional_order.render_selected',lambda *_:pytest.fail('unaccounted shapes'))
    restore_source_order(source,target,reports,Settings())
    assert target.read_bytes()==before and reports[1]['warnings']==['source_reading_order_unverified']
