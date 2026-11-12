from contextlib import closing
import numpy as np
import pypdfium2 as pdfium
from reportlab.pdfgen import canvas
from smartppt.layout import extract_native,page_background
from smartppt.regional import objects_for_page,regional_background,word_pixel_box


def test_symbol_glyphs_keep_exact_source_pixels_when_body_text_is_recovered(tmp_path):
 source=tmp_path/'symbols.pdf';c=canvas.Canvas(str(source),pagesize=(400,400))
 c.setFont('Helvetica',18);c.drawString(30,330,'Body text 123.45')
 c.setFont('Symbol',24);c.drawString(30,240,'α + β = γ');c.save()
 with pdfium.PdfDocument(source) as doc,closing(doc[0]) as page:
  runs,objects,warnings=extract_native(page,split_words=True)
  assert ''.join(r['text'] for r in runs)=='Body text 123.45'
  assert 'formula_or_symbol_font_kept_as_graphic' in warnings
  candidates,_=objects_for_page(page,word_regions=True)
  original=np.asarray(page_background(page,[],max_side=2200,scale_limit=2))
  restored=np.asarray(regional_background(page,candidates))
  # Formula lies well outside every recovered body's rectangle.
  assert np.array_equal(original[260:360],restored[260:360])
  assert not np.array_equal(original,restored)


def test_private_use_mapping_is_not_guessed_as_a_chinese_letter(tmp_path,monkeypatch):
 source=tmp_path/'private-glyph.pdf';c=canvas.Canvas(str(source),pagesize=(400,400));c.drawString(30,330,'Logo 123.45');c.save()
 actual=pdfium.raw.FPDFText_GetUnicode
 monkeypatch.setattr(pdfium.raw,'FPDFText_GetUnicode',lambda tp,i:0xE000 if i==0 else actual(tp,i))
 with pdfium.PdfDocument(source) as doc,closing(doc[0]) as page:
  runs,_,warnings=extract_native(page,split_words=True)
  assert not runs and 'unmapped_glyph_kept_as_graphic' in warnings
  candidates,_=objects_for_page(page,word_regions=True)
  assert [r['text'].strip() for _,rs in candidates for r in rs]==['123.45']
  original=np.asarray(page_background(page,[],max_side=2200,scale_limit=2));restored=np.asarray(regional_background(page,candidates))
  l,t,r,b=word_pixel_box(candidates[0][1][0]['box'],page.get_size());mask=np.ones(original.shape[:2],bool);mask[t:b,l:r]=False
  assert np.array_equal(original[mask],restored[mask])


def test_unicode_bullets_and_unit_symbols_do_not_rasterize_body(tmp_path):
 from smartppt.layout import graphical_text
 for name,text in [('SymbolMT','•••'),('CMMI10','µ.µ'),('CMSY10','×'),('CMMI10','.')]:
  assert not graphical_text(name,text)
 for name,text in [('CMMI10','x'),('CMSY10','∑'),('SymbolMT','α + β = γ')]:
  assert graphical_text(name,text)
 source=tmp_path/'bullet.pdf';c=canvas.Canvas(str(source),pagesize=(400,400));c.setFont('Symbol',18);c.drawString(20,300,'•');c.setFont('Helvetica',18);c.drawString(45,300,'Budget 123.45');c.save()
 with pdfium.PdfDocument(source) as doc,closing(doc[0]) as page:
  runs,_,warnings=extract_native(page)
  assert '•' in ''.join(r['text'] for r in runs)
  assert 'formula_or_symbol_font_kept_as_graphic' not in warnings
