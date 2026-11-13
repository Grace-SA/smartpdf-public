"""Adversarial synthetic checks: spatial mixups must not become editable text."""
from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path
import pytest
from PIL import Image, ImageDraw, ImageFont
import pypdfium2 as pdfium
from pptx import Presentation
from smartppt.assisted import ocr_slide
from smartppt.consensus import region_agreement, overlapping_lines
from smartppt.config import ConversionError


def evidence():
    def line(text, l, t, r, b):
        return {'text': text, 'confidence': .99, 'polygon': [[l,t],[r,t],[r,b],[l,b]]}
    record = {'input_sha256': 'digest', 'image_size': [400, 200], 'lines': [
        line('North 123.45', 10, 20, 160, 40), line('South 678.90', 220, 20, 390, 40)]}
    verifier = {'input_sha256': 'digest', 'image_size': [400, 200], 'capped': False,
                'coordinate_space': 'pixels', 'blocks': [
                    {'label': 'text', 'bbox': [5, 15, 165, 45], 'content': 'North 123.45'},
                    {'label': 'text', 'bbox': [215, 15, 395, 45], 'content': 'South 678.90'}]}
    return record, verifier


def test_column_values_cannot_be_swapped():
    record, verifier = evidence()
    assert region_agreement(record, verifier) == [True, True]
    verifier['blocks'][0]['content'] = 'North 678.90'
    verifier['blocks'][1]['content'] = 'South 123.45'
    assert region_agreement(record, verifier) == [False, False]


def test_local_disagreement_preserves_other_column():
    record, verifier = evidence(); verifier['blocks'][1]['content'] = 'South 678.99'
    assert region_agreement(record, verifier) == [True, False]


def test_word_order_cannot_be_approved_by_character_counts():
    record, verifier = evidence(); verifier['blocks'][0]['content'] = '123.45 North'
    assert region_agreement(record, verifier) == [False, True]


@pytest.mark.parametrize('label', ['table', 'formula', 'picture', 'chart', 'chemical equation'])
def test_nontext_structures_remain_images(label):
    record, verifier = evidence(); verifier['blocks'][0]['label'] = label
    assert region_agreement(record, verifier) == [False, True]


def test_exact_duplicate_or_nested_plain_regions_require_identical_text():
    record, verifier = evidence(); verifier['blocks'].append(deepcopy(verifier['blocks'][0]))
    assert region_agreement(record, verifier) == [True, True]
    verifier['blocks'][-1]['bbox'][0] += 1
    assert region_agreement(record, verifier) == [True, True]
    verifier['blocks'][-1]['content']='North 123.46'
    assert region_agreement(record, verifier) == [False, True]
    record, verifier = evidence()
    verifier['blocks'].append({'label': 'picture', 'bbox': [0,0,400,200], 'content': ''})
    assert region_agreement(record, verifier) == [False, False]


def test_simple_grid_requires_exact_cell_content_and_column_positions():
    record, verifier = evidence()
    verifier['blocks']=[{'label':'table','bbox':[0,0,400,100],
        'content':'<table><tr><td>North 123.45</td><td>South 678.90</td></tr></table>'}]
    assert region_agreement(record,verifier)==[True,True]
    verifier['blocks'][0]['content']='<table><tr><td>North 678.90</td><td>South 123.45</td></tr></table>'
    assert region_agreement(record,verifier)==[False,False]


@pytest.mark.parametrize('content', [
    '<table><tr><td colspan="2">North 123.45 South 678.90</td></tr></table>',
    '<table><tr><td>North 123.45</td><td></td><td>South 678.90</td></tr></table>',
    '<table><tr><td>North 123.45</td><td>South<br/>678.90</td></tr></table>',
    '<!DOCTYPE table [<!ENTITY a "North 123.45">]><table><tr><td>&a;</td><td>South 678.90</td></tr></table>'])
def test_unproven_table_structure_stays_raster(content):
    record,verifier=evidence();verifier['blocks']=[{'label':'table','bbox':[0,0,400,100],'content':content}]
    assert region_agreement(record,verifier)==[False,False]


@pytest.mark.parametrize('field,value,code', [
    ('input_sha256','wrong','ocr_provenance_mismatch'),
    ('image_size',[200,400],'ocr_geometry_mismatch'),
    ('coordinate_space','unknown','invalid_ocr_regions')])
def test_provenance_geometry_binding(field,value,code):
    record, verifier = evidence(); verifier[field] = value
    with pytest.raises(ConversionError, match=code): region_agreement(record, verifier)


@pytest.mark.parametrize('box', [[0,0,float('nan'),20],[-1,0,30,20],[0,0,401,20],[20,0,0,20]])
def test_invalid_region_boxes_fail_closed(box):
    record, verifier = evidence(); verifier['blocks'][0]['bbox'] = box
    with pytest.raises(ConversionError, match='invalid_ocr_regions'): region_agreement(record, verifier)


def test_capped_model_cannot_approve_any_region():
    record, verifier = evidence(); verifier['capped'] = True
    assert region_agreement(record, verifier) == [False,False]


def test_normalized_u2_coordinates_and_reading_order():
    record, verifier = evidence(); verifier['coordinate_space'] = 'normalized-1000'
    for b in verifier['blocks']:
        b['bbox'] = [v * (1000/400 if i%2 == 0 else 1000/200) for i,v in enumerate(b['bbox'])]
    assert region_agreement(record, verifier) == [True,True]
    verifier['blocks'][0]['page'] = 2
    with pytest.raises(ConversionError): region_agreement(record, verifier)


def test_erase_rectangle_overlap_includes_padding():
    record,_ = evidence(); record['lines'].append(deepcopy(record['lines'][0]))
    assert overlapping_lines(record['lines']) == {0,2}


@pytest.mark.parametrize('boxes,expected', [
    ([(5, 5, 20.1, 20), (22.2, 5, 40, 20)], {0, 1}),
    ([(5, 5, 20, 20.1), (5, 22.2, 20, 40)], {0, 1}),
    ([(5, 5, 20.1, 20.1), (22.2, 22.2, 40, 40)], {0, 1}),
    ([(5, 5, 20, 20), (22, 5, 40, 20)], set()),
    ([(5, 5, 20, 20), (5, 22, 20, 40)], set()),
])
def test_overlap_uses_actual_integer_erase_rectangles(boxes, expected):
    lines = [{'polygon': [[l, t], [r, t], [r, b], [l, b]]}
             for l, t, r, b in boxes]
    assert overlapping_lines(lines) == expected


@pytest.mark.parametrize("shared_ink",[False,True])
def test_fractional_overlap_only_preserves_original_raster_when_ink_intersects(tmp_path, pdf_file,shared_ink,monkeypatch):
    # This fixture isolates erasure geometry, not font recognition.
    monkeypatch.setattr("smartppt.assisted.latin_font",lambda *_:None)
    image = Image.new('RGB', (100, 60), 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, 18, 18), fill='black')
    draw.rectangle((25, 10, 35, 18), fill='black')
    if shared_ink:draw.point((21,12),fill='black')
    path = tmp_path/'fractional.png'
    image.save(path)
    record = {
        'input_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'image_size': [100, 60],
        'lines': [
            {'text': 'A', 'confidence': .99,
             'polygon': [[5, 5], [20.1, 5], [20.1, 25], [5, 25]]},
            {'text': 'B', 'confidence': .99,
             'polygon': [[22.2, 5], [40, 5], [40, 25], [22.2, 25]]},
        ],
    }
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    with pdfium.PdfDocument(pdf_file) as doc:
        report = ocr_slide(prs, slide, doc[0], path, record,
                           line_approvals=[True, True])
    assert report['editable_lines'] == (0 if shared_ink else 2)
    from io import BytesIO
    raster=Image.open(BytesIO(slide.shapes[0].image.blob))
    if shared_ink:
        assert 'overlapping_ocr_kept_as_image' in report['warnings']
        assert raster.tobytes()==image.tobytes()
    else:
        assert raster.getpixel((21,12))==image.getpixel((21,12))
        assert raster.getpixel((15,15))==(255,255,255)
        assert raster.getpixel((30,15))==(255,255,255)


@pytest.mark.parametrize('background,foreground', [((255,255,210),(20,40,100)),((220,240,255),(40,40,40))])
def test_tinted_paper_and_text_color_are_preserved(tmp_path,pdf_file,background,foreground):
    image = Image.new('RGB',(400,200),background); draw = ImageDraw.Draw(image)
    draw.text((12,20),'North 123.45',font=ImageFont.load_default(size=20),fill=foreground)
    path=tmp_path/'scan.png';image.save(path)
    record,_ = evidence(); record['lines']=record['lines'][:1]
    record['lines'][0]['polygon']=[[5,10],[180,10],[180,55],[5,55]]
    record['input_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    prs=Presentation();slide=prs.slides.add_slide(prs.slide_layouts[6])
    with pdfium.PdfDocument(pdf_file) as doc:
        result=ocr_slide(prs,slide,doc[0],path,record,line_approvals=[True])
    assert result['editable_lines']==1
    assert slide.shapes[1].text=='North 123.45'
    color=slide.shapes[1].text_frame.paragraphs[0].runs[0].font.color.rgb
    assert max(abs(a-b) for a,b in zip(color,foreground))<=10
    from io import BytesIO
    raster=Image.open(BytesIO(slide.shapes[0].image.blob))
    assert raster.getpixel((15,25))==background


def test_overlapping_detections_preserve_original_pixels(tmp_path,pdf_file):
    image=Image.new('RGB',(400,200),'white');ImageDraw.Draw(image).text((10,20),'North 123.45',fill='black')
    path=tmp_path/'scan.png';image.save(path);record,_=evidence()
    record['lines']=[record['lines'][0],deepcopy(record['lines'][0])]
    record['input_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    prs=Presentation();slide=prs.slides.add_slide(prs.slide_layouts[6])
    with pdfium.PdfDocument(pdf_file) as doc:
        result=ocr_slide(prs,slide,doc[0],path,record,line_approvals=[True,True])
    assert result['editable_lines']==0
    from io import BytesIO
    assert Image.open(BytesIO(slide.shapes[0].image.blob)).tobytes()==image.tobytes()


@pytest.mark.parametrize('url', ['https://free-oxr.somark.ai','http://localhost.evil:18081',
    'http://127.0.0.1:18081/path','http://user:pass@127.0.0.1:18081','http://127.0.0.1:18081?target=x'])
def test_oxr_refuses_nonlocal_detector(url):
    spec=importlib.util.spec_from_file_location('oxr_runner',Path(__file__).parents[1]/'ocr/oxr_runner.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    with pytest.raises(ValueError):module.local_url(url)


def test_scan_without_independent_verifier_stays_image_and_cleans_tempfiles(tmp_path,settings):
    from reportlab.pdfgen import canvas
    from smartppt.assisted import assist
    from smartppt.pdf import render_page
    image=tmp_path/'input.png';Image.new('RGB',(400,200),'white').save(image)
    source=tmp_path/'input.pdf';c=canvas.Canvas(str(source),pagesize=(200,100));c.drawImage(str(image),0,0,200,100);c.save()
    raster=tmp_path/'raster.png';render_page(source,0,max_side=1900).save(raster)
    record,_=evidence();record['input_sha256']=hashlib.sha256(raster.read_bytes()).hexdigest()
    prs=Presentation();prs.slides.add_slide(prs.slide_layouts[6]);target=tmp_path/'out.pptx';prs.save(target)
    settings.ocr_verifier_python=settings.ocr_verifier_runner=settings.oxr_python=settings.oxr_runner=''
    report=assist(source,target,settings,cached_ocr={0:record})
    assert report['pages'][0]['editable_lines']==0
    assert 'independent_ocr_verification_unavailable' in report['pages'][0]['warnings']
    assert not list(tmp_path.glob('smartppt-ocr-*'))


def test_pinned_artifact_tampering_is_rejected(tmp_path):
    spec=importlib.util.spec_from_file_location('integrity',Path(__file__).parents[1]/'ocr/integrity.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    path=tmp_path/'model';path.write_bytes(b'good')
    inventory={'model':{'bytes':4,'sha256':hashlib.sha256(b'good').hexdigest()}}
    module.verify_files(tmp_path,inventory)
    path.write_bytes(b'evil')
    with pytest.raises(ValueError,match='hash mismatch'):module.verify_files(tmp_path,inventory)


def test_isolated_scan_specks_do_not_inflate_glyph_height():
    import numpy as np
    from smartppt.assisted import coherent_ink
    mask=np.zeros((50,100),dtype=bool);mask[15:35,20:23]=True;mask[0,0]=True;mask[49,99]=True
    points=np.argwhere(coherent_ink(mask))
    assert points[:,0].min()==15 and points[:,0].max()==34
    assert points[:,1].min()==20 and points[:,1].max()==22
