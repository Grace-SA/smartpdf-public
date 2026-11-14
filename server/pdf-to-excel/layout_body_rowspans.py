"""Restore single-column body spans only from closed source-grid evidence.

Move an existing value, never infer or rewrite text. Two independent columns
must establish every source-to-model row correspondence in the entire span.
"""
from copy import deepcopy
from collections import defaultdict
import math
from itertools import accumulate
from pdfplumber.utils import extract_text
from layout_native_order import _box, _geometry, _inside, _overlap
from layout_native_colspans import _covered
from layout_nested_guard import closed_table
from layout_tables import physical_page, visible_box


def closed_side(edges, horizontal, position, start, end):
    # Native table detection snaps nearby parallel border strokes. Require an
    # actual fully covered side within that narrow border band, not whitespace.
    straight = []
    for e in edges:
        if e.get('object_type') not in ('line', 'rect_edge'):
            continue
        values = (e['x0'], e['top'], e['x1'], e['bottom'])
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values):
            continue
        fixed = (e['top']+e['bottom'])/2 if horizontal else (e['x0']+e['x1'])/2
        thickness = abs(e['bottom']-e['top']) if horizontal else abs(e['x1']-e['x0'])
        if thickness <= .1 and abs(fixed-position) <= 2:
            straight.append(e)
    positions = {(e['top']+e['bottom'])/2 if horizontal else (e['x0']+e['x1'])/2 for e in straight}
    return len(positions) <= 16 and any(_covered(straight, horizontal, p, start, end) for p in positions)


def compact(text):
    return ''.join(text.split())


def recover(model, native, page):
    try:
        return _recover(model, native, page)
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, OverflowError):
        return model


def _recover(model, native, page):
    if getattr(page, 'rotation', 0) or len(page.chars) > 50000:
        return model
    rows, cols = len(model['heights']), len(model['widths'])
    cells = model['cells']
    if not 5 <= rows <= 300 or not 3 <= cols <= 30 or len(cells) > rows * cols:
        return model
    if len(page.chars) * len(cells) > 2000000:
        return model
    by_col = defaultdict(list)
    used = {}
    for i, cell in enumerate(cells):
        if any(type(cell.get(k)) is not int for k in ('r', 'c', 'rs', 'cs')) or not isinstance(cell.get('text'), str):
            return model
        by_col[cell['c']].append((i, cell))
        if cell['text'].strip() and not _box(cell.get('sourceTextCandidate')):
            return model
        r, c, rs, cs = (cell[k] for k in ('r', 'c', 'rs', 'cs'))
        if not 0 <= r < r + rs <= rows or not 0 <= c < c + cs <= cols:
            return model
        for y in range(r, r + rs):
            for x in range(c, c + cs):
                if (y, x) in used:
                    return model
                used[y, x] = i
    view = visible_box(page)
    if not _box(view) or not _box(model['bbox']):
        return model
    candidates = [t for t in native if closed_table(t) and len(t['widths']) == cols
                  and _inside(t['bbox'], view) and _overlap(t['bbox'], model['bbox'])]
    # Nested/overlapping candidate grids are not an unambiguous row authority.
    if len(candidates) != 1:
        return model
    table = candidates[0]
    if len(table['cells']) * len(cells) > 500000:
        return model
    spans = [c for c in table['cells'] if c['cs'] == 1 and 2 <= c['rs'] <= 20 and c['text'].strip()]
    if len(spans) > 64:
        return model
    xs = list(accumulate(table['widths'], initial=table['bbox'][0]))
    ys = list(accumulate(table['heights'], initial=table['bbox'][1]))
    def bounds(c):
        return (xs[c['c']], ys[c['r']], xs[c['c']+c['cs']], ys[c['r']+c['rs']])
    chars = [g for g in page.chars if g.get('text', '').strip()]
    if any(not _box(_geometry(g)) for g in chars):
        return model
    physical = physical_page(page)
    edges = physical.edges
    if len(edges) > 10000:
        return model
    obstacles = []
    for group in (getattr(page, 'images', []), getattr(page, 'annots', [])):
        if not isinstance(group, list) or len(group) > 1000:
            return model
        for obj in group:
            box = _geometry(obj)
            if not _box(box):
                return model
            obstacles.append(box)
    by_row = defaultdict(list)
    for cell in table['cells']:
        by_row[cell['r']].append(cell)
    comparisons = 0
    changes = []
    for source in spans:
        if source['c'] >= cols or source['cs'] != 1 or not 2 <= source['rs'] <= 20 or source['r'] == 0 or not source['text'].strip():
            continue
        box = bounds(source)
        if any(_overlap(box, b) for b in obstacles):
            continue
        if not all(closed_side(edges, horizontal, position, start, end) for horizontal, position, start, end in
                   [(True, box[1], box[0], box[2]), (True, box[3], box[0], box[2]),
                    (False, box[0], box[1], box[3]), (False, box[2], box[1], box[3])]):
            continue
        matches = [(i, c) for i, c in by_col[source['c']] if c['cs'] == c['rs'] == 1
                   and c['text'].strip() and _box(c.get('sourceTextCandidate'))
                   and _inside(c['sourceTextCandidate'], box) and compact(c['text']) == compact(source['text'])]
        if len(matches) != 1:
            continue
        index, target = matches[0]
        glyphs = [g for g in chars if _overlap(_geometry(g), box)]
        if not glyphs or any(not _inside(_geometry(g), box) or not _inside(_geometry(g), view)
                             or not (target['sourceTextCandidate'][0] <= (g['x0']+g['x1'])/2 <= target['sourceTextCandidate'][2]
                                     and target['sourceTextCandidate'][1] <= (g['top']+g['bottom'])/2 <= target['sourceTextCandidate'][3])
                             or not g.get('upright') or not g.get('matrix') or len(g['matrix']) != 6
                             or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in g['matrix'])
                             or g['matrix'][0] <= 0 or g['matrix'][3] <= 0
                             or abs(g['matrix'][1]) > .001 or abs(g['matrix'][2]) > .001 for g in glyphs):
            continue
        if any(i != index and c['text'].strip()
               and any(c['sourceTextCandidate'][0] <= (g['x0']+g['x1'])/2 <= c['sourceTextCandidate'][2]
                       and c['sourceTextCandidate'][1] <= (g['top']+g['bottom'])/2 <= c['sourceTextCandidate'][3] for g in glyphs)
               for i, c in enumerate(cells)):
            continue
        if compact(extract_text(glyphs, x_tolerance=2, y_tolerance=3)) != compact(target['text']):
            continue
        mapped = []
        for row in range(source['r'], source['r'] + source['rs']):
            evidence = []
            for anchor in by_row[row]:
                if anchor['r'] != row:
                    continue
                if anchor['rs'] != 1 or anchor['cs'] != 1 or anchor['c'] == source['c'] or not anchor['text'].strip():
                    continue
                ab = bounds(anchor)
                comparisons += len(by_col[anchor['c']])
                if comparisons > 500000:
                    return model
                hits = [c for _, c in by_col[anchor['c']] if c['rs'] == c['cs'] == 1
                        and c['text'].strip() and _box(c.get('sourceTextCandidate'))
                        and _inside(c['sourceTextCandidate'], ab) and compact(c['text']) == compact(anchor['text'])]
                if len(hits) == 1:
                    evidence.append((anchor['c'], hits[0]['r']))
            if len({c for c, r in evidence}) < 2 or len({r for c, r in evidence}) != 1:
                break
            mapped.append(evidence[0][1])
        if len(mapped) != source['rs'] or mapped != list(range(mapped[0], mapped[0]+len(mapped))) or mapped[0] < 3 or target['r'] not in mapped:
            continue
        consumed = {used[r, source['c']] for r in mapped if (r, source['c']) in used}
        if any(i != index and (cells[i]['text'].strip() or cells[i]['cs'] != 1 or cells[i]['rs'] != 1) for i in consumed):
            continue
        changes.append((index, consumed - {index}, mapped[0], len(mapped)))
    if not changes or len({i for _, gone, _, _ in changes for i in gone}) != sum(len(gone) for _, gone, _, _ in changes):
        return model
    result = deepcopy(model)
    removed = set()
    for index, gone, start, span in changes:
        result['cells'][index].update(r=start, rs=span)
        removed.update(gone)
    result['cells'] = [c for i, c in enumerate(result['cells']) if i not in removed]
    occupied = set()
    for c in result['cells']:
        slots = {(r, col) for r in range(c['r'], c['r']+c['rs']) for col in range(c['c'], c['c']+c['cs'])}
        if occupied & slots:
            return model
        occupied.update(slots)
    return result
