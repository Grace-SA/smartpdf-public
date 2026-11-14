"""Flag source-proven split header phrases without guessing cell ownership."""
import math
from statistics import median

NOTICE = ("A parenthesized header phrase may be split across cells. "
          "Its target column and merge span are unverified. Cell text and structure "
          "were left unchanged; check the original PDF before interpreting units or headings.")


def compact(text):
    return ''.join(text.split())


def split_header_phrase(table, page):
    """Narrow, advisory-only native evidence; never reconstruct a header."""
    if (getattr(page, 'rotation', 0) or not table.get('method', '').startswith('layout')
            or not hasattr(page, 'extract_words')):
        return False
    cells = sorted((c for c in table['cells'] if c['r'] == 0 and c['text'].strip()),
                   key=lambda c: c['c'])
    if not 2 <= len(cells) <= 12:
        return False
    words = page.extract_words(x_tolerance=2, y_tolerance=3)
    if len(words) > 16000:
        return False
    for left, right in zip(cells, cells[1:]):
        if (left['rs'] != 1 or right['rs'] != 1 or left['cs'] < 2 or right['cs'] != 1
                or left['c'] + left['cs'] != right['c']):
            continue
        a, b = left.get('sourceTextCandidate'), right.get('sourceTextCandidate')
        if any(not isinstance(box, (list, tuple)) or len(box) != 4
               or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in box)
               or box[0] >= box[2] or box[1] >= box[3] for box in (a, b)):
            continue
        # Only a trailing unmatched parenthesis joined to a closing fragment.
        text = left['text']; opening = text.rfind('(')
        if (opening <= 0 or not text[:opening].strip() or ')' in text[opening:]
                or text[:opening].count('(') != text[:opening].count(')')
                or '(' in right['text'] or right['text'].count(')') != 1
                or not right['text'].rstrip().endswith(')')):
            continue
        selected = []
        valid = True
        for box, cell in ((a, left), (b, right)):
            group = [w for w in words if w.get('upright')
                     and box[0] <= (w['x0']+w['x1'])/2 <= box[2]
                     and box[1] <= (w['top']+w['bottom'])/2 <= box[3]]
            group.sort(key=lambda w: w['x0'])
            if not group or compact(' '.join(w['text'] for w in group)) != compact(cell['text']):
                valid = False
                break
            selected.extend(group)
        if not valid or not 3 <= len(selected) <= 40:
            continue
        h = median(w['bottom']-w['top'] for w in selected)
        if (not 3 <= h <= 40 or any(w['bottom']-w['top'] > h*1.2 for w in selected)
                or max(w['top'] for w in selected)-min(w['top'] for w in selected) > 1
                or any(y['x0'] < x['x1'] for x,y in zip(selected, selected[1:]))):
            continue
        starts = [i for i,w in enumerate(selected) if w['text'].startswith('(')
                  and compact(' '.join(v['text'] for v in selected[:i])) == compact(text[:opening])]
        if len(starts) != 1 or starts[0] == 0:
            continue
        i = starts[0]; phrase = selected[i:]
        if (selected[i]['x0']-selected[i-1]['x1'] <= h*1.5
                or any(y['x0']-x['x1'] > h*.65 for x,y in zip(phrase,phrase[1:]))):
            continue
        joined = ''.join(w['text'] for w in phrase)
        if joined.count('(') == joined.count(')') == 1 and joined.endswith(')'):
            return True
    return False
