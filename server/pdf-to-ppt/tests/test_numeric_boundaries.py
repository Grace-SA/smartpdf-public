from collections import Counter
from smartppt.quality import numeric_tokens


def test_date_comma_is_not_a_partial_thousands_group():
 assert numeric_tokens('January 1,1990')==numeric_tokens('January 1, 1990')==Counter({'1':1,'1990':1})
 assert numeric_tokens('January 1,1991')!=numeric_tokens('January 1,1990')
 assert numeric_tokens('12,345,678.90%')==Counter({'12,345,678.90%':1})
 assert numeric_tokens('12,345,67')==Counter({'12':1,'345':1,'67':1})
 assert numeric_tokens('1,234, 567')==Counter({'1,234':1,'567':1})


def test_lost_minus_or_decimal_is_a_numeric_error():
 assert numeric_tokens('−123.45')==numeric_tokens('-123.45')==Counter({'-123.45':1})
 assert numeric_tokens('−123.45')!=numeric_tokens('123.45')
 assert numeric_tokens('.5%')==Counter({'.5%':1})
 assert numeric_tokens('.5%')!=numeric_tokens('5%')
 assert numeric_tokens('-.25')==Counter({'-.25':1})
 assert numeric_tokens('Total １２３．４５')==numeric_tokens('Total 123.45')


def test_date_does_not_hide_an_actual_changed_financial_number(tmp_path):
 from pptx import Presentation
 from smartppt.quality import inspect_pptx
 p=Presentation();slide=p.slides.add_slide(p.slide_layouts[6]);shape=slide.shapes.add_textbox(0,0,1000000,1000000)
 reference='January 1,1990. Revenue −123.45; rate .5%.'
 info={'page_count':1,'mixed_sizes':False,'pages':[{'number':1,'text':reference,'needs_ocr_check':False}]}
 target=tmp_path/'test.pptx'
 for text,expected in [('January 1, 1990. Revenue -123.45; rate .5%.',False),('January 1, 1990. Revenue 123.45; rate .5%.',True),('January 1, 1990. Revenue −123.45; rate 5%.',True)]:
  shape.text=text;p.save(target);warnings=inspect_pptx(target,info,'editable')['warnings']
  assert any(w['code']=='numeric_mismatch' for w in warnings)==expected
