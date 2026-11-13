import os
from contextlib import closing
import pytest
import pypdfium2 as pdfium
from pptx import Presentation
from smartppt.layout import add_text
from smartppt.config import Settings
from smartppt.render_gate import render_presentations
from smartppt.quality import normalized

@pytest.mark.parametrize('family,key',[('SmartPDF Sans100','SMARTPPT_CJK_FONT'),('SmartPDF Serif200','SMARTPPT_CJK_SERIF_FONT')])
def test_renderer_uses_exact_static_family_instead_of_variable_regular(tmp_path,family,key):
 if not os.getenv(key) or not os.getenv('SMARTPPT_TEST_RENDERER'):pytest.skip('pinned font and actual renderer required')
 p=Presentation();s=p.slides.add_slide(p.slide_layouts[6]);text='项目预算123.45 Revenue 678.90'
 add_text(s,text,30,40,600,50,22,family);target=tmp_path/'font.pptx';p.save(target)
 pdf=render_presentations([target],tmp_path,Settings(renderer_path=os.environ['SMARTPPT_TEST_RENDERER']))[0]
 with pdfium.PdfDocument(pdf) as doc,closing(doc[0]) as page,closing(page.get_textpage()) as tp:
  assert normalized(tp.get_text_range())==normalized(text)
  names=[o.get_font().get_base_name() for o in page.get_objects(filter=[pdfium.raw.FPDF_PAGEOBJ_TEXT])]
  assert names and all(family.replace(' ','') in name for name in names),names
 assert (tmp_path/'approved-static-fonts').is_dir()


def test_static_words_preserve_complete_numbers_and_skip_rotated_lines(tmp_path):
 if not os.getenv('SMARTPPT_CJK_FONT') or not os.getenv('SMARTPPT_TEST_RENDERER'):pytest.skip('pinned font and actual renderer required')
 from smartppt.portable_fonts import split_script_shapes
 p=Presentation();s=p.slides.add_slide(p.slide_layouts[6])
 text='Revenue -123.45 Total 678.90%'
 add_text(s,text,30,40,600,40,18,'SmartPDF Sans100')
 rotated=add_text(s,'Rotated 234.56 text',30,140,500,40,18,'SmartPDF Sans100');rotated.rotation=2
 original=rotated._element.xml;target=tmp_path/'words.pptx';p.save(target)
 pdf=render_presentations([target],tmp_path,Settings(renderer_path=os.environ['SMARTPPT_TEST_RENDERER']))[0]
 targets=split_script_shapes(p,pdf)
 assert len(targets[0])==4 and all(row['kind']=='font-words' for row in targets[0])
 assert [shape.text.strip() for shape in s.shapes if not shape.rotation]==['Revenue','-123.45','Total','678.90%']
 assert rotated._element.xml==original
 assert len({shape.shape_id for shape in s.shapes})==len(s.shapes)
