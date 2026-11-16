import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('u2_parser',Path(__file__).resolve().parents[1]/'ocr/u2_parser.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def test_title_text_and_table_blocks():
    blocks=module.parse_blocks('<PAGE><BLOCK>title<LEVEL1>[10, 20, 800, 90]<FORK>标题\n<BLOCK>table[10,100,800,500]<FORK><table><tr><td>123.45</td></tr></table>')
    assert blocks[0]['content']=='标题' and blocks[0]['level']==1
    assert blocks[1]['bbox']==[10,100,800,500] and '<td>123.45</td>' in blocks[1]['content']

@pytest.mark.parametrize('raw',['garbage','<PAGE><BLOCK>text[9,1,2,30]<FORK>x','<PAGE><BLOCK>text[1,1,1001,30]<FORK>x'])
def test_invalid_model_output_rejected(raw):
    with pytest.raises(ValueError):module.parse_blocks(raw)

def test_blank_page_keeps_page_identity():
    blocks=module.parse_blocks('<PAGE><PAGE><BLOCK>text[1,1,20,30]<FORK>Second page')
    assert blocks[0]['page']==2
