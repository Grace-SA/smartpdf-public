"""Reject proven short-label order loss in native nested-table reconstruction.

This is a refusal check, not a general nested-table detector or span repair.
No values, characters, model geometry or PDF content are modified.
"""
from collections import Counter
from itertools import accumulate

from pdfplumber.utils import extract_text, cluster_objects
from layout_native_order import _box, _geometry, _inside, _overlap, _finite
from layout_tables import LayoutError, visible_box


def verify_nested_labels(model, native, page):
    try:
        _verify(model, native, page)
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, OverflowError):
        return


def closed_table(table):
    if not table.get('closedGrid') or not _box(table.get('bbox')):
        return False
    widths, heights, cells = table.get('widths', []), table.get('heights', []), table.get('cells', [])
    if not 2 <= len(widths) <= 30 or not 2 <= len(heights) <= 300 or len(cells) > 9000:
        return False
    if any(not _finite(v) or v <= 0 for v in widths + heights):
        return False
    box = table['bbox']
    if abs(sum(widths) - box[2] + box[0]) > 1 or abs(sum(heights) - box[3] + box[1]) > 1:
        return False
    used = set()
    for c in cells:
        if any(type(c.get(k)) is not int for k in ('r', 'c', 'rs', 'cs')) or not isinstance(c.get('text'), str):
            return False
        r, col, rs, cs = (c[k] for k in ('r', 'c', 'rs', 'cs'))
        if not 0 <= r < r + rs <= len(heights) or not 0 <= col < col + cs <= len(widths):
            return False
        slots = {(y, x) for y in range(r, r + rs) for x in range(col, col + cs)}
        if slots & used:
            return False
        used.update(slots)
    return len(used) == len(widths) * len(heights)


def strictly_contains(outer, inner):
    return (all(inner[i] > outer[i] + 1 for i in (0, 1))
            and all(inner[i] < outer[i] - 1 for i in (2, 3)))


def _verify(model, native, page):
    if getattr(page, 'rotation', 0) or not 2 <= len(native) <= 100:
        return
    mcells = model['cells']
    if not 1 <= len(mcells) <= 9000 or len(page.chars) > 50000:
        return
    valid = [t for t in native if closed_table(t)]
    pairs = [(parent, child) for parent in valid for child in valid
             if parent is not child and strictly_contains(parent['bbox'], child['bbox'])]
    if len(pairs) != 1 or len(pairs[0][0]['cells']) * len(mcells) > 500000:
        return
    parent, child = pairs[0]
    xs = list(accumulate(parent['widths'], initial=parent['bbox'][0]))
    ys = list(accumulate(parent['heights'], initial=parent['bbox'][1]))
    containers = [c for c in parent['cells'] if strictly_contains(
        (xs[c['c']], ys[c['r']], xs[c['c'] + c['cs']], ys[c['r'] + c['rs']]), child['bbox'])]
    if len(containers) != 1:
        return
    parents = [parent]
    view = visible_box(page)
    if not _box(view):
        return
    obstacles = []
    for objects in (getattr(page, 'images', []), getattr(page, 'annots', [])):
        if not isinstance(objects, list) or len(objects) > 1000:
            return
        for obj in objects:
            b = _geometry(obj)
            if not _box(b):
                return
            obstacles.append(b)
    nonempty = [c for c in mcells if c['text'].strip()]
    if any(not _box(c.get('sourceTextCandidate')) for c in nonempty):
        return
    chars = [g for g in page.chars if g['text'].strip()]
    if any(not _box(_geometry(g)) for g in chars):
        return
    for parent in parents:
        xs = list(accumulate(parent['widths'], initial=parent['bbox'][0]))
        ys = list(accumulate(parent['heights'], initial=parent['bbox'][1]))
        for cell in parent['cells']:
            text = cell['text']
            if (not text.isascii() or not 2 <= len(text.split()) <= 12
                    or len(text) > 200 or any(ch.isdigit() for ch in text)
                    or cell['cs'] != 1):
                continue
            r, c, rs = cell['r'], cell['c'], cell['rs']
            box = (xs[c], ys[r], xs[c + 1], ys[r + rs])
            if (not _box(box) or not _inside(box, view) or _overlap(child['bbox'], box)
                    or any(_overlap(o, box) for o in obstacles)):
                continue
            pieces = [m for m in nonempty if _overlap(m['sourceTextCandidate'], box)]
            if not 2 <= len(pieces) <= 4 or any(
                not _inside(m['sourceTextCandidate'], box) or m['cs'] != 1 for m in pieces
            ):
                continue
            # Only vertical fragmentation of a single logical column is admitted.
            if len({m['c'] for m in pieces}) != 1 or len({m['r'] for m in pieces}) != len(pieces):
                continue
            glyphs = [g for g in chars if _overlap(_geometry(g), box)]
            if not glyphs or len(glyphs) > 200 or any(
                not _inside(_geometry(g), box) or not g.get('upright')
                or len(g.get('matrix', ())) != 6
                or not all(_finite(v) for v in g['matrix'])
                or g['matrix'][0] <= 0 or g['matrix'][3] <= 0
                or abs(g['matrix'][1]) > 0.001 or abs(g['matrix'][2]) > 0.001
                for g in glyphs
            ):
                continue
            if (any(not _finite(g.get('size')) or not 6 <= g['size'] <= 24 for g in glyphs)
                    or max(g['size'] for g in glyphs) - min(g['size'] for g in glyphs) > 0.1
                    or len({g.get('fontname') for g in glyphs}) != 1):
                continue
            lines = cluster_objects(glyphs, lambda g: g['matrix'][5], 0.5)
            lines.sort(key=lambda line: min(g['top'] for g in line))
            if not 2 <= len(lines) <= 4 or any(
                max(g['bottom'] for g in a) >= min(g['top'] for g in b)
                for a, b in zip(lines, lines[1:])
            ):
                continue
            if extract_text(glyphs, x_tolerance=2, y_tolerance=3).split() != text.split():
                continue
            if any(sum(_inside(_geometry(g), m['sourceTextCandidate'], 1.5)
                       for m in pieces) != 1 for g in glyphs):
                continue
            values = [m['text'] for m in sorted(pieces, key=lambda m: (m['r'], m['c']))]
            words = ' '.join(values).split()
            if Counter(words) == Counter(text.split()) and words != text.split():
                raise LayoutError(
                    'A nested table reconstruction reversed a source label. Its outer records could not be preserved reliably; use an unnested table version.'
                )
