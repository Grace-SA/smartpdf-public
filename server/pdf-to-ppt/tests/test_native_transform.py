from contextlib import closing
import pytest
import pypdfium2 as pdfium
from reportlab.pdfgen import canvas
from pypdf import PdfReader,PdfWriter
from smartppt.layout import extract_native

@pytest.mark.parametrize('page_rotation',[0,90,180,270])
@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('shear',[0,.2126])
def test_synthetic_italic_keeps_baseline_rotation_and_perpendicular_font_height(tmp_path,page_rotation,rotation,shear):
 p=tmp_path/'transform.pdf';c=canvas.Canvas(str(p),pagesize=(400,600));c.translate(200,300);c.rotate(rotation);c.transform(1,0,shear,1,0,0);c.setFont('Helvetica',12);c.drawString(0,0,'North 123.45');c.save()
 if page_rotation:
  w=PdfWriter();w.add_page(PdfReader(p).pages[0].rotate(page_rotation))
  with p.open('wb') as f:w.write(f)
 with pdfium.PdfDocument(p) as doc,closing(doc[0]) as page:
  runs,objects,warnings=extract_native(page,split_words=True,allow_quarter_turns=True)
 assert [r['text'].strip() for r in runs]==['North','123.45']
 assert all(r['rotation']==(page_rotation-rotation)%360 for r in runs)
 assert all(r['size']==pytest.approx(12,abs=.001) for r in runs)
 assert all(r['italic']==bool(shear) for r in runs)
 assert not warnings

@pytest.mark.parametrize('shear',[-.2126,.05,.5])
def test_unsupported_shear_remains_source_graphic(tmp_path,shear):
 p=tmp_path/'shear.pdf';c=canvas.Canvas(str(p),pagesize=(400,400));c.translate(100,200);c.transform(1,0,shear,1,0,0);c.drawString(0,0,'Keep original 123');c.save()
 with pdfium.PdfDocument(p) as doc,closing(doc[0]) as page:
  runs,objects,warnings=extract_native(page,split_words=True,allow_quarter_turns=True)
 assert not runs and not objects
 assert 'unsupported_text_shear_kept_as_graphic' in warnings

@pytest.mark.parametrize('a,d',[(-1,1),(1,-1)])
def test_mirrored_glyphs_are_not_replaced_with_unmirrored_text(tmp_path,a,d):
 p=tmp_path/'mirror.pdf';c=canvas.Canvas(str(p),pagesize=(400,400));c.translate(200,200);c.transform(a,0,0,d,0,0);c.drawString(0,0,'Mirror 123');c.save()
 with pdfium.PdfDocument(p) as doc,closing(doc[0]) as page:
  runs,objects,warnings=extract_native(page,split_words=True,allow_quarter_turns=True)
 assert not runs and not objects
 assert 'unresolved_character' in warnings

@pytest.mark.parametrize('nested',[False,True])
@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_generated_spacing_uses_real_neighbor_transform_without_splitting_paragraph(tmp_path,nested,rotation):
 p=tmp_path/'positioned.pdf';c=canvas.Canvas(str(p),pagesize=(600,600))
 c.translate(300,300);c.rotate(rotation)
 if nested:c.beginForm('positioned')
 # The gap becomes a PDFium-generated space with an identity character
 # matrix. The visible glyphs have a 12x text transform, inside an optional form.
 c._code.append('BT /F1 1 Tf 12 0 0 12 0 0 Tm [(Alpha) -300 (Beta)] TJ ET')
 if nested:c.endForm();c.scale(1.5,1.5);c.doForm('positioned')
 c.save()
 with pdfium.PdfDocument(p) as doc,closing(doc[0]) as page,closing(page.get_textpage()) as tp:
  assert tp.get_text_range()=='Alpha Beta'
  assert pdfium.raw.FPDFText_IsGenerated(tp,5)==1
  runs,objects,warnings=extract_native(page,allow_quarter_turns=True)
 assert len(runs)==1 and runs[0]['text']=='Alpha Beta'
 assert runs[0]['size']==pytest.approx(18 if nested else 12)
 assert runs[0]['rotation']==(-rotation)%360
 assert not warnings

@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('page_rotation',[0,90,180,270])
def test_scaled_quoted_words_use_baseline_not_punctuation_ink_bottom(tmp_path,rotation,page_rotation):
 p=tmp_path/'quoted.pdf';c=canvas.Canvas(str(p),pagesize=(500,500));c.translate(250,250);c.rotate(rotation);c.scale(.82816,.82816);c.setFont('Helvetica',8)
 c.drawString(0,0,'Labels "C" "L" "U" "X" gyp');c.save()
 if page_rotation:
  writer=PdfWriter();writer.add_page(PdfReader(p).pages[0].rotate(page_rotation))
  with p.open('wb') as f:writer.write(f)
 with pdfium.PdfDocument(p) as doc,closing(doc[0]) as page:
  runs,_,warnings=extract_native(page,split_words=True,allow_quarter_turns=True)
 assert [r['text'].strip() for r in runs]==['Labels','"C"','"L"','"U"','"X"','gyp']
 assert not warnings


def test_same_object_superscript_does_not_merge_with_baseline(tmp_path):
 p=tmp_path/'raised.pdf';c=canvas.Canvas(str(p),pagesize=(300,300));c._code.append('BT /F1 10 Tf 30 200 Td (Base) Tj 4 Ts (Raised) Tj 0 Ts (End) Tj ET');c.save()
 with pdfium.PdfDocument(p) as doc,closing(doc[0]) as page:
  runs,_,_=extract_native(page)
 assert [r['text'] for r in runs]==['Base','Raised','End']
