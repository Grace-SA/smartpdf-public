"""Refuse repeated numeric-column collapse against a visible physical grid.

This is a structural uncertainty guard, NOT a native-text recovery or proof that
all native glyphs are visible. It never copies, splits or reassigns values. In
particular, ICC color profiles and reverse text do not authorize reconstruction.
"""
from collections import defaultdict
from itertools import accumulate
import math
import re

import numpy as np
from pdfplumber.utils import extract_text
from pdfplumber.utils.exceptions import MalformedPDFException
from layout_tables import LayoutError, visible_box
from layout_native_order import _box, _geometry, _inside, _overlap, _finite
from layout_nested_guard import closed_table
from layout_split_rows import visible_sides

_NUMBER = re.compile(r'[+-]?(?:\d+(?:[.,]\d+)*|\.\d+)%?\Z')
NOTICE = ('Repeated numeric cells conflict with separately bounded source columns. '
          'The converter cannot safely verify their row and column ownership; '
          'conversion was stopped rather than exporting potentially mixed values.')


def verify_numeric_columns(model, native, page):
    try:
        conflict = _conflict(model, native, page)
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, OverflowError,
            OSError, RuntimeError, MalformedPDFException):
        return
    if conflict:
        raise LayoutError(NOTICE)


def _conflict(model, native, page):
    if (getattr(page, 'rotation', 0) or tuple(page.bbox) != (0, 0, page.width, page.height)
            or tuple(page.cropbox) != tuple(page.mediabox)):
        return False
    cells = model['cells']; chars = [g for g in page.chars if g['text'].strip()]
    if (not 1 <= len(cells) <= 9000 or not 1 <= len(chars) <= 50000
            or not 1 <= len(native) <= 100 or len(cells)*len(chars) > 2_000_000):
        return False
    rows, cols = len(model['heights']), len(model['widths'])
    if not 1 <= rows <= 300 or not 2 <= cols <= 30:
        return False
    if any(any(type(c.get(k)) is not int for k in ('r', 'c', 'rs', 'cs'))
           or not 0 <= c['r'] < c['r']+c['rs'] <= rows
           or not 0 <= c['c'] < c['c']+c['cs'] <= cols for c in cells):
        return False
    candidates = [c for c in cells if c.get('rs') == c.get('cs') == 1
                  and isinstance(c.get('text'), str) and len(c['text']) <= 100
                  and len(c['text'].split()) == 2
                  and all(_NUMBER.fullmatch(t) for t in c['text'].split())
                  and _box(c.get('sourceTextCandidate'))]
    if len(candidates) < 3 or len(chars)*len(candidates) > 2_000_000:
        return False
    if any(not _box(_geometry(g)) for g in chars):
        return False
    tables = [t for t in native if closed_table(t)]
    if sum(len(t['cells']) for t in tables)*len(chars) > 5_000_000:
        return False
    view = visible_box(page); rendered = None
    for table in tables:
        if not _inside(table['bbox'], view):
            continue
        # Competing/nested native tables cannot establish unique ownership.
        if any(other is not table and _overlap(other['bbox'], table['bbox']) for other in tables):
            continue
        xs = list(accumulate(table['widths'], initial=table['bbox'][0]))
        ys = list(accumulate(table['heights'], initial=table['bbox'][1]))
        values = []
        for c in table['cells']:
            if c['rs'] != 1 or c['cs'] != 1 or not _NUMBER.fullmatch(c['text'].strip()):
                continue
            box = (xs[c['c']], ys[c['r']], xs[c['c']+1], ys[c['r']+1])
            glyphs = [g for g in chars if _overlap(_geometry(g), box)]
            if (not glyphs or any(not _inside(_geometry(g), box) for g in glyphs)
                    or any(not g.get('upright') or len(g.get('matrix', ())) != 6
                           or any(not _finite(v) for v in g['matrix'])
                           or g['matrix'][0] <= 0 or g['matrix'][3] <= 0
                           or abs(g['matrix'][1]) > .001 or abs(g['matrix'][2]) > .001 for g in glyphs)
                    or max(g['matrix'][5] for g in glyphs)-min(g['matrix'][5] for g in glyphs) > .5
                    or ''.join(extract_text(glyphs).split()) != c['text'].strip()):
                continue
            values.append((c, box, glyphs))
        if len(values)*len(candidates) > 500_000:
            continue
        hits = defaultdict(list)
        for c in candidates:
            b = c['sourceTextCandidate']
            selected = [(n, box, glyphs) for n, box, glyphs in values
                        if all(b[0] <= (g['x0']+g['x1'])/2 <= b[2]
                               and b[1] <= (g['top']+g['bottom'])/2 <= b[3] for g in glyphs)]
            if len(selected) != 2:
                continue
            selected.sort(key=lambda v: v[0]['c'])
            (left, a, ga), (right, b2, gb) = selected
            if (left['r'] != right['r'] or left['c']+1 != right['c']
                    or c['text'].split() != [left['text'].strip(), right['text'].strip()]):
                continue
            # Complete character ownership in the model bbox, not value lookup.
            owned = [g for g in chars if b[0] <= (g['x0']+g['x1'])/2 <= b[2]
                     and b[1] <= (g['top']+g['bottom'])/2 <= b[3]]
            if (max(g['matrix'][5] for g in ga+gb)-min(g['matrix'][5] for g in ga+gb) > .5
                    or {id(g) for g in owned} != {id(g) for g in ga+gb}):
                continue
            if any(other is not c and other.get('text', '').strip()
                   and _box(other.get('sourceTextCandidate'))
                   and any(other['sourceTextCandidate'][0] <= (g['x0']+g['x1'])/2 <= other['sourceTextCandidate'][2]
                           and other['sourceTextCandidate'][1] <= (g['top']+g['bottom'])/2 <= other['sourceTextCandidate'][3]
                           for g in owned) for other in cells):
                continue
            if rendered is None:
                if math.ceil(page.width*2)*math.ceil(page.height*2) > 20_000_000:
                    return False
                rendered = np.asarray(page.to_image(resolution=144).original.convert('L'))
            if visible_sides(rendered, a, page.width, page.height) and visible_sides(rendered, b2, page.width, page.height):
                hits[(c['c'], left['c'])].append((c['r'], left['r']))
        # One numeric spanning header is not evidence of collapsed body columns.
        for pairs in hits.values():
            if len({r for r, _ in pairs}) >= 3 and len({r for _, r in pairs}) >= 3:
                return True
    return False
