"""Synthetic TOC and ambiguous-layout regressions; no corpus text or images."""
from copy import deepcopy
import pytest
from smartppt.consensus import region_agreement, row_order


def evidence():
    def line(text, x, y, width=150, height=20):
        return {'text': text, 'confidence': .99,
                'polygon': [[x,y],[x+width,y],[x+width,y+height],[x,y+height]]}
    record = {'input_sha256': 'synthetic', 'image_size': [500,150], 'lines': [
        line('First section',10,20), line('7',450,17,20,26),
        line('Second section',10,65), line('18',440,62,30,26)]}
    verifier = {'input_sha256': 'synthetic', 'image_size': [500,150],
                'capped': False, 'coordinate_space': 'pixels', 'blocks': [
                    {'label':'text','bbox':[0,0,500,140],
                     'content':'First section 7\nSecond section 18'}]}
    return record, verifier


def test_different_glyph_heights_preserve_title_number_order():
    record, verifier = evidence()
    before = deepcopy(record)
    assert region_agreement(record,verifier) == [True]*4
    assert record == before


@pytest.mark.parametrize('content', [
    'First section 18\nSecond section 7',
    '7 First section\n18 Second section',
    'Second section 18\nFirst section 7',
    'First section 70\nSecond section 180',
    'First section\nSecond section\n7\n18',
])
def test_wrong_numbers_or_column_major_text_cannot_authorize_page_numbers(content):
    record, verifier = evidence()
    verifier['blocks'][0]['content'] = content
    approved = region_agreement(record,verifier)
    assert not approved[1] and not approved[3]


@pytest.mark.parametrize('ambiguous', ['angle','overlap','touch','bridge'])
def test_uncertain_geometry_preserves_original_order(ambiguous):
    record, _ = evidence()
    lines = record['lines']
    if ambiguous == 'angle':
        lines[0]['polygon'][1][1] += 8
    elif ambiguous in ('overlap','touch'):
        x = 100 if ambiguous == 'overlap' else 160
        lines[1]['polygon'] = [[x,17],[230,17],[230,43],[x,43]]
    else:
        lines.append({'text':'ambiguous', 'polygon':[[200,25],[300,25],[300,80],[200,80]]})
    original = sorted(range(len(lines)),key=lambda i:(min(p[1] for p in lines[i]['polygon']),min(p[0] for p in lines[i]['polygon'])))
    assert row_order(lines,list(range(len(lines)))) == original


def test_conflicting_nested_region_vetoes_row_recovery():
    record, verifier = evidence()
    verifier['blocks'].append({'label':'text','bbox':[0,0,500,50],'content':'First section 18'})
    assert region_agreement(record,verifier)[:2] == [False,False]


def test_separate_columns_use_their_own_spatial_evidence():
    record, verifier = evidence()
    verifier['blocks'] = [
        {'label':'text','bbox':[0,0,200,140],'content':'First section\nSecond section'},
        {'label':'text','bbox':[400,0,500,140],'content':'7\n18'}]
    assert region_agreement(record,verifier) == [True]*4
    verifier['blocks'][1]['content'] = '18\n7'
    assert region_agreement(record,verifier) == [True,False,True,False]
