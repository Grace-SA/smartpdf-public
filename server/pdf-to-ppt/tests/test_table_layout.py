from copy import deepcopy
from contextlib import closing
import os
import pytest
import pypdfium2 as pdfium
from pptx import Presentation
from pptx.util import Pt
from pptx.enum.text import MSO_ANCHOR
from smartppt.config import ConversionError
from smartppt.layout import add_text
from smartppt.table_layout import bind_cells,build_hybrid,align_cells,try_restore_tables,portable_cell_insets
from smartppt.portable_fonts import font_shapes


def table_slide():
    prs=Presentation();prs.slide_width=Pt(400);prs.slide_height=Pt(300)
    slide=prs.slides.add_slide(prs.slide_layouts[6])
    frame=slide.shapes.add_table(2,2,Pt(20),Pt(60),Pt(300),Pt(100))
    for i,text in enumerate(['Alpha 12','Beta 34','Gamma 56','Delta 78']):
        cell=frame.table.cell(i//2,i%2);cell.text=text;cell.vertical_anchor=MSO_ANCHOR.MIDDLE
        cell.margin_top=cell.margin_bottom=0
        for run in cell.text_frame.paragraphs[0].runs:run.font.name='Arial';run.font.size=Pt(12)
    return prs,slide,frame


def targets():
    return [{'shape':i+1,'source_index':i*10,'text':text,'bbox':box} for i,(text,box) in enumerate([
        ('Heading',(20,20,80,30)),('Alpha 12',(25,75,80,85)),('Beta 34',(175,75,230,85)),
        ('Gamma 56',(25,125,90,135)),('Delta 78',(175,125,230,135))])]


def test_bind_cells_preserves_occurrence_order_and_rejects_wrong_cell():
    _,slide,table=table_slide();bound=bind_cells(slide,targets())
    assert bound is not None and bound[1]=={2,3,4,5}
    assert [[t['source_index'] for t in ts] for _,ts in bound[0]]==[[10],[20],[30],[40]]
    table.table.cell(0,0).text='Beta 34';table.table.cell(0,1).text='Alpha 12'
    assert bind_cells(slide,targets()) is None


def test_merged_cell_and_ambiguous_overlapping_tables():
    _,slide,frame=table_slide();frame.table.cell(0,0).merge(frame.table.cell(0,1))
    bound=bind_cells(slide,targets());assert bound is not None
    assert len(bound[0])==3 and bound[1]=={2,3,4,5}
    slide.shapes._spTree.insert_element_before(deepcopy(frame._element),'p:extLst')
    assert bind_cells(slide,targets()) is None


def test_source_word_crossing_cell_border_is_not_claimed():
    _,slide,_=table_slide();rows=targets();rows[1]['bbox']=(0,75,80,85)
    assert bind_cells(slide,rows) is None


def test_hybrid_preserves_cell_merges_text_and_unique_shape_ids():
    _,original,frame=table_slide();frame.table.cell(0,0).merge(frame.table.cell(0,1))
    prs=Presentation();slide=prs.slides.add_slide(prs.slide_layouts[6])
    add_text(slide,'placeholder',0,0,1,1,1)
    for row in targets():add_text(slide,row['text'],*row['bbox'][:2],100,20,12)
    before=[(cell.text,dict(cell._tc.attrib)) for row in frame.table.rows for cell in row.cells]
    bound=build_hybrid(slide,original,targets());assert bound is not None
    assert [s.text for s in slide.shapes if s.has_text_frame]==['Heading']
    table=next(s.table for s in slide.shapes if s.has_table)
    assert [(cell.text,dict(cell._tc.attrib)) for row in table.rows for cell in row.cells]==before
    ids=[s.shape_id for s in slide.shapes];assert len(ids)==len(set(ids))
    assert slide.shapes[0].text=='Heading'


def test_picture_under_native_text_is_not_retained_as_a_second_copy(tmp_path):
    from PIL import Image,ImageDraw
    _,original,_=table_slide();picture=tmp_path/'graphic.png';image=Image.new('RGB',(20,20),'white')
    ImageDraw.Draw(image).text((2,3),'old',fill='black');image.save(picture)
    original.shapes.add_picture(str(picture),Pt(20),Pt(60),Pt(100),Pt(40))
    prs=Presentation();slide=prs.slides.add_slide(prs.slide_layouts[6])
    add_text(slide,'placeholder',0,0,1,1,1)
    for row in targets():add_text(slide,row['text'],*row['bbox'][:2],100,20,12)
    before=slide._element.xml
    assert build_hybrid(slide,original,targets()) is None
    assert slide._element.xml==before


def test_redundant_raster_grid_is_removed_but_native_cells_and_logo_remain(tmp_path):
    from io import BytesIO
    from PIL import Image,ImageDraw
    from smartppt.table_layout import table_decoration
    base,original,frame=table_slide();image=Image.new('RGBA',(300,100),(0,0,0,0));draw=ImageDraw.Draw(image)
    draw.rectangle((0,0,299,99),outline='black');draw.line((150,0,150,99),fill='black');draw.line((0,50,299,50),fill='black')
    path=tmp_path/'ruling.png';image.save(path)
    picture=original.shapes.add_picture(str(path),frame.left,frame.top,frame.width,frame.height)
    assert table_decoration(picture,frame)
    logo=tmp_path/'logo.png';Image.new('RGB',(10,10),'red').save(logo)
    original.shapes.add_picture(str(logo),Pt(350),Pt(20),Pt(10),Pt(10))
    stream=BytesIO();base.save(stream);stream.seek(0);prs=Presentation(stream);slide=prs.slides[0]
    for shape in list(slide.shapes):shape._element.getparent().remove(shape._element)
    add_text(slide,'placeholder',0,0,1,1,1)
    for row in targets():add_text(slide,row['text'],*row['bbox'][:2],100,20,12)
    assert build_hybrid(slide,original,targets()) is not None
    assert sum(s.has_table for s in slide.shapes)==1
    pictures=[s for s in slide.shapes if hasattr(s,'image')]
    assert len(pictures)==1 and pictures[0].left==Pt(350)
    assert pictures[0].image.blob==logo.read_bytes()
    picture.rotation=15;assert not table_decoration(picture,frame)


def test_unverified_border_strip_is_not_left_behind_when_table_moves(tmp_path):
    from PIL import Image
    _,original,frame=table_slide();path=tmp_path/'strip.png';Image.new('RGB',(300,1),'black').save(path)
    original.shapes.add_picture(str(path),frame.left,frame.top,frame.width,Pt(.4))
    prs=Presentation();slide=prs.slides.add_slide(prs.slide_layouts[6]);add_text(slide,'placeholder',0,0,1,1,1)
    for row in targets():add_text(slide,row['text'],*row['bbox'][:2],100,20,12)
    before=slide._element.xml
    assert build_hybrid(slide,original,targets()) is None and slide._element.xml==before


@pytest.mark.parametrize('transparent',[False,True])
def test_uniform_heading_background_does_not_discard_separate_table(tmp_path,transparent):
    from io import BytesIO
    from PIL import Image
    base,original,_=table_slide();path=tmp_path/'heading-fill.png'
    image=Image.new('RGBA',(100,20),(255,255,255,0 if transparent else 255))
    if transparent:image.putpixel((8,8),(31,77,89,0))
    image.save(path);original.shapes.add_picture(str(path),Pt(20),Pt(20),Pt(100),Pt(20))
    stream=BytesIO();base.save(stream);stream.seek(0);prs=Presentation(stream);slide=prs.slides[0]
    for shape in list(slide.shapes):shape._element.getparent().remove(shape._element)
    add_text(slide,'placeholder',0,0,1,1,1)
    for row in targets():add_text(slide,row['text'],*row['bbox'][:2],100,20,12)
    assert build_hybrid(slide,original,targets()) is not None
    assert sum(s.has_table for s in slide.shapes)==1
    assert [s.text for s in slide.shapes if s.has_text_frame]==['Heading']
    assert [s.image.blob for s in slide.shapes if hasattr(s,'image')]==[path.read_bytes()]


@pytest.mark.parametrize('pixel',[(254,255,255,255),(255,255,255,254)])
def test_nonuniform_heading_image_cannot_hide_duplicate_letters(tmp_path,pixel):
    from PIL import Image
    from smartppt.table_layout import flat_background
    _,original,_=table_slide();path=tmp_path/'heading-ink.png'
    image=Image.new('RGBA',(100,20),'white');image.putpixel((8,8),pixel);image.save(path)
    picture=original.shapes.add_picture(str(path),Pt(20),Pt(20),Pt(100),Pt(20))
    assert not flat_background(picture)
    prs=Presentation();slide=prs.slides.add_slide(prs.slide_layouts[6]);add_text(slide,'placeholder',0,0,1,1,1)
    for row in targets():add_text(slide,row['text'],*row['bbox'][:2],100,20,12)
    before=slide._element.xml
    assert build_hybrid(slide,original,targets()) is None and slide._element.xml==before


def test_separate_vector_border_cannot_masquerade_as_native_cell_border():
    from pptx.enum.shapes import MSO_CONNECTOR
    _,original,frame=table_slide()
    original.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,frame.left,frame.top,frame.left+frame.width,frame.top)
    prs=Presentation();slide=prs.slides.add_slide(prs.slide_layouts[6]);add_text(slide,'placeholder',0,0,1,1,1)
    for row in targets():add_text(slide,row['text'],*row['bbox'][:2],100,20,12)
    before=slide._element.xml
    assert build_hybrid(slide,original,targets()) is None and slide._element.xml==before


def test_vertical_fit_measures_top_anchor_again_without_growing_bottom_padding():
    _,slide,frame=table_slide();bound=bind_cells(slide,targets())[0]
    cell,words=bound[0];observed={t['shape']:(t['bbox'][0],t['bbox'][1]+3,t['bbox'][2],t['bbox'][3]+3) for t in words}
    height=frame.height;bottom=cell.margin_bottom
    assert align_cells([(cell,words)],observed)
    assert cell.vertical_anchor==MSO_ANCHOR.TOP and cell.margin_top==0
    observed={t['shape']:(t['bbox'][0],t['bbox'][1]-3,t['bbox'][2],t['bbox'][3]-3) for t in words}
    assert align_cells([(cell,words)],observed)
    assert cell.margin_top==Pt(3) and cell.margin_bottom==bottom and frame.height==height
    assert not align_cells([(cell,words)],{})
    observed[words[0]['shape']]=(25,70,80,90)
    assert not align_cells([(cell,words)],observed)


def test_horizontal_cell_translation_preserves_width_and_requires_every_word():
    from pptx.enum.text import PP_ALIGN
    from smartppt.table_layout import align_cell_horizontal
    _,_,frame=table_slide();cell=frame.table.cell(0,0)
    cell.text_frame.paragraphs[0].alignment=PP_ALIGN.LEFT
    words=[{'shape':1,'bbox':(25,75,50,85)},{'shape':2,'bbox':(55,75,80,85)}]
    observed={1:(25,75,49,85),2:(53.5,75,77.7,85)};width=cell.margin_left+cell.margin_right;left=cell.margin_left
    assert align_cell_horizontal(cell,words,observed)
    assert cell.margin_left==left+Pt(1.15) and cell.margin_left+cell.margin_right==width
    snapshot=cell._tc.xml
    assert not align_cell_horizontal(cell,words,{1:observed[1]})
    assert not align_cell_horizontal(cell,words,{1:(25,75,49,85),2:(53.5,95,77.7,105)})
    assert not align_cell_horizontal(cell,words,{1:(25,75,49,85),2:(50,75,74,85)})
    assert cell._tc.xml==snapshot
    cell.margin_right=0
    assert not align_cell_horizontal(cell,words,observed)


def test_cell_fonts_are_included_in_portable_font_inventory():
    prs,_,frame=table_slide();frame.table.cell(0,0).text_frame.paragraphs[0].runs[0].font.name='Noto Serif SC'
    frames=font_shapes(prs);assert len(frames)==1
    assert frames[0][0]==0 and frames[0][1]._tc is frame.table.cell(0,0)._tc


def test_uniform_paragraph_right_padding_survives_as_cell_padding():
    _,_,frame=table_slide();cell=frame.table.cell(0,0);before=cell.margin_right
    p=cell.text_frame.paragraphs[0];p._p.get_or_add_pPr().set('marR',str(Pt(2.5)))
    other=cell.text_frame.add_paragraph();other.text='Next 91';other._p.get_or_add_pPr().set('marR',str(Pt(2.5)))
    portable_cell_insets(cell)
    assert cell.margin_right==before+Pt(2.5)
    assert all(p._p.pPr.get('marR')=='0' for p in cell.text_frame.paragraphs)
    portable_cell_insets(cell);assert cell.margin_right==before+Pt(2.5)
    p._p.pPr.set('marR',str(Pt(3)));snapshot=cell._tc.xml
    portable_cell_insets(cell);assert cell._tc.xml==snapshot


def test_optional_table_render_failure_is_not_published(monkeypatch):
    import smartppt.table_layout as module
    def fail(*args,**kwargs):raise ConversionError('layout_render_failed')
    monkeypatch.setattr(module,'restore_tables',fail)
    assert try_restore_tables()==({},None)


@pytest.mark.skipif(not os.getenv('SMARTPPT_TEST_RENDERER'),reason='real Office renderer required')
def test_real_table_repair_keeps_native_cells_and_source_text(tmp_path,settings):
    from smartppt.render_gate import render_presentations
    from smartppt.native_words import try_native_words
    from smartppt.quality import normalized,shape_text
    settings.renderer_path=os.environ['SMARTPPT_TEST_RENDERER']
    prs,slide,frame=table_slide();add_text(slide,'Header 90',20,20,130,25,12)
    source_ppt=tmp_path/'source.pptx';prs.save(source_ppt)
    source=render_presentations([source_ppt],tmp_path,settings)[0]
    frame.table.cell(0,0).margin_top=Pt(12)
    target=tmp_path/'damaged.pptx';prs.save(target)
    report={'pages':[{'page':1,'route':'stirling-table','warnings':[]}]}
    try_native_words(source,target,report,settings)
    result=Presentation(target);page=report['pages'][0]
    assert page['route']=='stirling-table' and page['table_layout']['tables']==1
    assert page['table_layout']['position_passed']>0
    assert [[c.text for c in row.cells] for row in next(s.table for s in result.slides[0].shapes if s.has_table).rows]==[
        ['Alpha 12','Beta 34'],['Gamma 56','Delta 78']]
    with pdfium.PdfDocument(source) as doc,closing(doc[0]) as p,closing(p.get_textpage()) as tp:
        assert normalized(''.join(shape_text(result.slides[0].shapes)))==normalized(tp.get_text_range())


@pytest.mark.skipif(not os.getenv('SMARTPPT_TEST_RENDERER'),reason='real Office renderer required')
def test_real_office_save_keeps_right_aligned_cell_text_positions(tmp_path,settings):
    import subprocess
    from pptx.enum.text import PP_ALIGN
    from smartppt.layout import extract_native
    from smartppt.table_layout import word_targets
    from smartppt.ocr_fit import observed_boxes
    from smartppt.render_gate import render_presentations
    from smartppt.quality import normalized
    settings.renderer_path=os.environ['SMARTPPT_TEST_RENDERER']
    prs,_,frame=table_slide()
    for row in frame.table.rows:
        for cell in row.cells:
            p=cell.text_frame.paragraphs[0];p.alignment=PP_ALIGN.RIGHT
            p._p.get_or_add_pPr().set('marR',str(Pt(5)))
    source=tmp_path/'source.pptx';prs.save(source)
    baseline=render_presentations([source],tmp_path,settings)[0]
    with pdfium.PdfDocument(baseline) as doc,closing(doc[0]) as page:
        runs,_,_=extract_native(page,split_words=True)
        targets=word_targets(prs,page,[(None,runs)])
        with closing(page.get_textpage()) as tp:expected=normalized(tp.get_text_range())
    for row in frame.table.rows:
        for cell in row.cells:portable_cell_insets(cell)
    candidate=tmp_path/'portable.pptx';prs.save(candidate)
    saved=tmp_path/'saved';saved.mkdir()
    env=dict(os.environ,FONTCONFIG_FILE=str(tmp_path/'fonts.conf'),XDG_CACHE_HOME=str(tmp_path/'cache'),TMPDIR=str(tmp_path))
    subprocess.run([settings.renderer_path,'-env:UserInstallation='+(tmp_path/'save-profile').as_uri(),
        '--headless','--convert-to','pptx:Impress MS PowerPoint 2007 XML','--outdir',str(saved),str(candidate)],
        env=env,capture_output=True,check=True,timeout=60)
    restored=Presentation(saved/candidate.name)
    assert sum(s.has_table for s in restored.slides[0].shapes)==1
    output=render_presentations([saved/candidate.name],tmp_path,settings)[0]
    reference=Presentation();slide=reference.slides.add_slide(reference.slide_layouts[6]);add_text(slide,'placeholder',0,0,1,1,1)
    for t in targets:add_text(slide,t['text'],0,0,100,20,12)
    with pdfium.PdfDocument(output) as doc,closing(doc[0]) as page:
        found=observed_boxes(page,slide,targets)
        assert targets and all(t['shape'] in found and max(abs(a-b) for a,b in zip(t['bbox'],found[t['shape']]))<=2 for t in targets)
        with closing(page.get_textpage()) as tp:assert normalized(tp.get_text_range())==expected
