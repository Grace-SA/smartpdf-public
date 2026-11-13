"""Diagnostic tooling must not confuse text matching with geometric truth."""
import importlib.util
from pathlib import Path
import pytest

@pytest.fixture
def compare_module():
 path=Path(__file__).parents[1]/'tools'/'public-native-compare.py'
 spec=importlib.util.spec_from_file_location('public_native_compare',path)
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 return module


def word(text,left):return {'text':text,'bbox':[left,10,left+10,20]}


def test_geometry_pairing_does_not_relocate_swapped_numbers(compare_module,monkeypatch):
 reference=[word('123',10),word('456',100)]
 predicted=[word('456',10),word('123',100)]
 monkeypatch.setattr(compare_module,'words',lambda path:[((200,200),reference if path=='source' else predicted)])
 result=compare_module.compare('source','rendered')[0]
 assert result['exact_words']==result['strict_words']==0


def test_duplicate_geometry_and_extra_pages_are_not_silent_success(compare_module,monkeypatch):
 words=[word('A',10),word('A',10)]
 monkeypatch.setattr(compare_module,'words',lambda path:[((200,200),words)])
 assert compare_module.compare('source','rendered')[0]['strict_words']==0
 monkeypatch.setattr(compare_module,'words',lambda path:[((200,200),words)]*(1 if path=='source' else 2))
 with pytest.raises(ValueError,match='page count'):compare_module.compare('source','rendered')


def test_different_canvas_sizes_need_explicit_transform(compare_module,monkeypatch):
 monkeypatch.setattr(compare_module,'words',lambda path:[((200 if path=='source' else 400,200),[word('A',10)])])
 with pytest.raises(ValueError,match='dimensions'):compare_module.compare('source','rendered')


def test_text_and_geometry_must_both_pass(compare_module,monkeypatch):
 monkeypatch.setattr(compare_module,'words',lambda path:[((200,200),[word('123',10 if path=='source' else 13)])])
 result=compare_module.compare('source','rendered')[0]
 assert result['exact_words']==1 and result['strict_words']==0


def test_extra_rendered_words_remain_visible(compare_module,monkeypatch):
 reference=[word('A',10)];predicted=reference+[word('extra',100)]
 monkeypatch.setattr(compare_module,'words',lambda path:[((200,200),reference if path=='source' else predicted)])
 result=compare_module.compare('source','rendered')[0]
 assert result['strict_words']==1
 assert result['unpaired_rendered_words']==1
 assert result['unpaired_rendered']==[predicted[1]]
