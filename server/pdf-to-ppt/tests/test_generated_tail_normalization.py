"""Trim inferred separators only; never grant provenance or concatenate words."""
import ctypes
from copy import deepcopy
from contextlib import closing
from types import SimpleNamespace
import pytest
import pypdfium2 as pdfium
from smartppt.word_clusters import trim_generated_tails,source_verified

class TextPage:
    def __init__(self,text,generated):self.text=text;self.generated=generated
    def close(self):pass
    def count_chars(self):return len(self.text)
    def get_textobj(self,index):return SimpleNamespace(raw=ctypes.c_void_p(123))


def fake(monkeypatch,text,generated=()):
    tp=TextPage(text,set(generated));page=SimpleNamespace(get_textpage=lambda:tp)
    monkeypatch.setattr(pdfium.raw,'FPDFText_GetUnicode',lambda tp,i:ord(tp.text[i]))
    monkeypatch.setattr(pdfium.raw,'FPDFText_IsGenerated',lambda tp,i:1 if i in tp.generated else 0)
    return page


def run(text='Alpha ',**changes):
    result=dict(text=text,index=0,end_index=len(text),object_id=123,box=(10,10,50,20),
                baseline=10,rotation=0,font='Arial',size=12,bold=False,italic=False,
                source_base_font='Helvetica',color=(0,0,0),blocked_boxes=[(0,0,1,1)])
    result.update(changes);return result


def test_single_generated_terminal_space_is_pure_copied_normalization(monkeypatch):
    page=fake(monkeypatch,'Alpha ',[5]);original=run();before=deepcopy(original)
    assert not source_verified(page,[original])
    result=trim_generated_tails(page,[original])
    assert original==before and result[0] is not original
    assert result[0]['blocked_boxes'] is not original['blocked_boxes']
    assert result[0]['text']=='Alpha' and result[0]['end_index']==5
    assert result[0]['generated_tail_space_trimmed'] is True
    assert result[0]['source_original_end_index']==6
    assert source_verified(page,result)
    for key,value in original.items():
        if key not in ('text','end_index'):assert result[0][key]==value
    assert trim_generated_tails(page,result)==result

@pytest.mark.parametrize('text,generated',[
    ('Alpha ',()), # actual encoded space stays literal
    ('Alpha  ',(5,6)), # never peel a series of separators
    ('Alpha\t',(5,)),('Alpha\n',(5,)),('Alpha\u00a0',(5,)),
    ('Al pha ',(2,6)), # internal generated separators remain untrusted
    ('Alpha ',(0,5)), # generated visible glyph cannot be disguised by trimming
    (' ',(0,)),('Alpha',(4,)),('Alpha\t ',(6,))])
def test_no_other_characters_or_spaces_are_trimmed(monkeypatch,text,generated):
    page=fake(monkeypatch,text,generated);original=run(text)
    assert trim_generated_tails(page,[original])==[original]
    if generated:assert not source_verified(page,[original])

@pytest.mark.parametrize('changes',[{'text':'Alphx '},{'index':-1},{'end_index':5},
    {'end_index':7},{'index':True},{'text':'Ａlpha '},{'text':'Alpha  '}])
def test_original_text_and_range_must_match_exactly(monkeypatch,changes):
    page=fake(monkeypatch,'Alpha ',[5]);original=run(**changes)
    assert trim_generated_tails(page,[original])==[original]


def test_normalization_does_not_grant_owner_authority(monkeypatch):
    page=fake(monkeypatch,'Alpha ',[5]);original=run(object_id=999)
    trimmed=trim_generated_tails(page,[original])
    assert trimmed[0]['text']=='Alpha'
    assert not source_verified(page,trimmed)


def test_multiple_words_remain_separate_and_real_internal_space_is_preserved(monkeypatch):
    page=fake(monkeypatch,'A B 123 456',[3,7])
    runs=[run('A B ',end_index=4),run('123 ',index=4,end_index=8),run('456',index=8,end_index=11)]
    trimmed=trim_generated_tails(page,runs)
    assert [r['text'] for r in trimmed]==['A B','123','456']
    assert [r['index'] for r in trimmed]==[0,4,8]
    assert source_verified(page,trimmed)
    from smartppt.quality import numeric_tokens
    # The consumer must keep shapes separate, not concatenate stripped strings.
    assert numeric_tokens('\n'.join(r['text'] for r in trimmed))==numeric_tokens('A B 123 456')


def test_real_pdfium_generated_tj_gap_still_requires_strict_source_verification(tmp_path):
    from reportlab.pdfgen import canvas
    source=tmp_path/'generated-space.pdf';c=canvas.Canvas(str(source),pagesize=(216,216))
    c._code.append('BT /F1 12 Tf 30 100 Td [(Alpha) -400 (Beta)] TJ ET');c.save()
    with pdfium.PdfDocument(source) as doc,closing(doc[0]) as page,closing(page.get_textpage()) as tp:
        text=''.join(chr(pdfium.raw.FPDFText_GetUnicode(tp,i)) for i in range(tp.count_chars()))
        assert text=='Alpha Beta'
        assert pdfium.raw.FPDFText_IsGenerated(tp,5)==1
        owner=ctypes.cast(tp.get_textobj(0).raw,ctypes.c_void_p).value
        original=run(object_id=owner)
        assert not source_verified(page,[original])
        trimmed=trim_generated_tails(page,[original])
        assert trimmed[0]['text']=='Alpha' and source_verified(page,trimmed)
        assert original['text']=='Alpha '
