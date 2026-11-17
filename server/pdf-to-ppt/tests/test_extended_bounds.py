from copy import deepcopy

import numpy as np
import pytest

from smartppt.ocr_bounds import extend_tight_padding
from smartppt.consensus import erase_bounds, overlapping_lines


def detection():
    return {'text': 'Revenue 123.45', 'confidence': .99,
            'polygon': [[11, 11], [89, 11], [89, 29], [11, 29]]}


@pytest.mark.parametrize('background', [(255, 255, 255), (16, 48, 110)])
@pytest.mark.parametrize('extra', [1, 2])
def test_tight_detection_gets_only_bounded_empty_border(background, extra):
    image = np.full((50, 110, 3), background, dtype=np.uint8)
    image[11-extra:29+extra, 15:85] = (50, 50, 50)
    original = [detection()]
    before = deepcopy(original)
    refined, changed = extend_tight_padding(image, original)
    assert changed == [0] and original == before
    assert erase_bounds(refined[0]) == (10-extra, 10-extra, 90+extra, 30+extra)
    assert refined[0]['text'] == original[0]['text']
    assert refined[0]['confidence'] == original[0]['confidence']


@pytest.mark.parametrize('condition', ['nonuniform', 'ink_on_ring', 'slanted', 'edge', 'already_empty'])
def test_uncertain_or_unnecessary_expansion_keeps_original(condition):
    image = np.full((50, 110, 3), 255, dtype=np.uint8)
    image[10:30, 15:85] = 0
    original = [detection()]
    if condition == 'nonuniform':
        image[:, :50] = (200, 220, 240)
    elif condition == 'ink_on_ring':
        image[8:10, 40] = 0
    elif condition == 'slanted':
        original[0]['polygon'][1][1] += 1
    elif condition == 'edge':
        for point in original[0]['polygon']:
            point[1] -= 10
    else:
        image[:] = 255
    before = deepcopy(original)
    assert extend_tight_padding(image, original) == (before, [])
    assert original == before


def test_expansion_is_subject_to_normal_neighbor_overlap_veto():
    image = np.full((50, 110, 3), 255, dtype=np.uint8)
    image[10:30, 15:85] = 0
    neighbor = {'text': 'Other', 'confidence': 1.,
                'polygon': [[30, 29], [70, 29], [70, 40], [30, 40]]}
    refined, changed = extend_tight_padding(image, [detection(), neighbor])
    assert 0 in changed
    assert overlapping_lines(refined, image) == {0, 1}
