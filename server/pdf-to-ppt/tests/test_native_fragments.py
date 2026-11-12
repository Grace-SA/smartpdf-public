from contextlib import closing
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
import pypdfium2 as pdfium
from pptx import Presentation
from pptx.util import Pt
from smartppt.layout import extract_native,merge_native_runs,native_slide
from smartppt.assisted import content_error
from smartppt.quality import shape_text


def fragmented(path):
    c=canvas.Canvas(str(path),pagesize=(600,800));c.setFont('Helvetica',12)
    for text,start,y in [('North 123.45',40,700),('South 678.90',330,700),('Total 802.35',40,660)]:
        t=c.beginText();t.setFont('Helvetica',12);t.setTextOrigin(start,y)
        for char in text:
            t.textOut(char)
        c.drawText(t)
    c.save()


def test_glyph_objects_form_complete_numbers_without_crossing_columns(tmp_path):
    source=tmp_path/'fragmented.pdf';fragmented(source)
    with pdfium.PdfDocument(source) as doc,closing(doc[0]) as page:
        original,objects,_=extract_native(page);grouped=merge_native_runs(page,original)
        assert len(original)>20 and len(objects)>20
        assert [r['text'] for r in grouped]==['North 123.45','South 678.90','Total 802.35']
        assert all(len(r['text'])==1 for r in original)  # grouping must not mutate object provenance
        p=Presentation();p.slide_width=Pt(600);p.slide_height=Pt(800)
        native_slide(p,page)
        actual='\n'.join(shape_text(p.slides[0].shapes))
        assert content_error('North 123.45\nSouth 678.90\nTotal 802.35',actual)==0
        from smartppt.pdf import inspect_pdf
        assert content_error(inspect_pdf(source)['pages'][0]['text'],actual)==0


def test_styles_and_non_whitespace_source_gaps_are_not_merged(tmp_path):
    source=tmp_path/'fragmented.pdf';fragmented(source)
    with pdfium.PdfDocument(source) as doc,closing(doc[0]) as page:
        runs,_,_=extract_native(page)
        first=runs[:2];first[1]=dict(first[1],bold=not first[0]['bold'])
        assert len(merge_native_runs(page,first))==2
        # Removing a middle glyph from the candidate list must never erase or
        # silently invent that missing character during presentation grouping.
        last=dict(runs[2],box=runs[1]['box'])
        assert len(merge_native_runs(page,[runs[0],last]))==2


def test_reference_cannot_drop_an_unresolved_source_character(tmp_path):
    from smartppt.layout import reference_text
    source=tmp_path/'fragmented.pdf';fragmented(source)
    with pdfium.PdfDocument(source) as doc,closing(doc[0]) as page,closing(page.get_textpage()) as tp:
        original=tp.get_text_range()+'UNRESOLVED'
        assert reference_text(page,original)==original


def test_tracking_does_not_invent_a_separator_between_source_digits(tmp_path):
    source=tmp_path/'fragmented.pdf';fragmented(source)
    with pdfium.PdfDocument(source) as doc,closing(doc[0]) as page:
        runs,_,_=extract_native(page);a=dict(runs[0],text='1');b=dict(runs[1],text='2',index=a['end_index'])
        b['box']=[a['box'][2]+4,a['box'][1],a['box'][2]+9,a['box'][3]]
        assert merge_native_runs(page,[a,b])[0]['text']=='12'


def test_regional_group_keeps_all_underlying_glyph_objects_atomic(tmp_path):
    from smartppt.regional import objects_for_page,draw_objects
    source=tmp_path/'fragmented.pdf';fragmented(source)
    with pdfium.PdfDocument(source) as doc,closing(doc[0]) as page:
        objects,_=objects_for_page(page)
        assert len(objects)==3 and all(len(group)>5 for group,parts in objects)
        assert [parts[0]['text'] for group,parts in objects]==['North 123.45','South 678.90','Total 802.35']
        prs=Presentation();prs.slide_width=Pt(600);prs.slide_height=Pt(800);slide=prs.slides.add_slide(prs.slide_layouts[6])
        draw_objects(prs,slide,page,objects[:1])
        assert shape_text(slide.shapes)==['North 123.45']
        # Background rendering restores every source object, including grouped
        # glyphs. A later source extraction must remain byte-for-byte identical.
        again,_=objects_for_page(page)
        assert [parts[0]['text'] for group,parts in again]==[parts[0]['text'] for group,parts in objects]


def test_upload_preflight_does_not_repeat_font_geometry_work(tmp_path,monkeypatch):
    from smartppt.pdf import inspect_pdf
    source=tmp_path/'fragmented.pdf';fragmented(source);calls=[]
    def reference(page,text):calls.append(1);return text
    monkeypatch.setattr('smartppt.layout.reference_text',reference)
    assert inspect_pdf(source,coordinate_reference=False)['page_count']==1 and not calls
    assert inspect_pdf(source)['page_count']==1 and calls==[1]
