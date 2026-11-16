from pptx import Presentation
from pptx.oxml.ns import qn
from smartppt.layout import add_text
from smartppt.ocr_fit import fit_local
from smartppt.paragraph_metrics import explicit_line_metrics, set_line_metrics


def shape():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    return add_text(slide, 'Total -123.45', 30, 40, 200, 40, 18, 'Arial', italic=True)


def test_single_line_defaults_follow_the_measured_font_size():
    item = shape()
    assert not explicit_line_metrics(item)
    set_line_metrics(item)
    assert explicit_line_metrics(item)
    assert fit_local(item, (30, 40, 162, 62), (30, 40, 150, 60))
    paragraph = item.text_frame.paragraphs[0]
    props = paragraph.runs[0]._r.rPr
    assert paragraph.line_spacing == paragraph.runs[0].font.size
    for node in [paragraph._p.pPr.find(qn('a:defRPr')), paragraph._p.find(qn('a:endParaRPr'))]:
        assert node.get('sz') == props.get('sz')
        assert node.get('i') == '1'
        assert node.find(qn('a:latin')).get('typeface') == 'Arial'
    assert item.text == 'Total -123.45'
    before = item._element.xml
    set_line_metrics(item)
    assert item._element.xml == before


def test_native_default_spacing_is_not_changed_by_fitting():
    item = shape()
    assert fit_local(item, (30, 40, 162, 62), (30, 40, 150, 60))
    assert item.text_frame.paragraphs[0].line_spacing is None
    assert not explicit_line_metrics(item)


def test_multiline_shapes_do_not_get_single_line_metrics():
    item = shape()
    item.text_frame.add_paragraph().text = 'Second line 678.90'
    before = item._element.xml
    set_line_metrics(item)
    assert item._element.xml == before
    assert not explicit_line_metrics(item)
