"""Native complex grids drawn with narrow filled rules, with explicit cell ownership."""
from statistics import median
from model import Rejected


def enclosed(inner, outer, pad=.5):
    return (inner[0] >= outer[0]-pad and inner[1] >= outer[1]-pad
            and inner[2] <= outer[2]+pad and inner[3] <= outer[3]+pad)


def visible_spaces(chars):
    """Discard stray space glyphs painted over letters, not word separators."""
    letters = [c for c in chars if c['text'].strip()]
    result = []
    for c in chars:
        area = (c['x1']-c['x0'])*(c['bottom']-c['top'])
        if not c['text'].strip() and area > 0 and any(
            max(0,min(c['x1'],v['x1'])-max(c['x0'],v['x0'])) *
            max(0,min(c['bottom'],v['bottom'])-max(c['top'],v['top'])) > .3*area
            for v in letters):
            continue
        result.append(c)
    return result


def reconstruct(page, words):
    from layout import native_tables, words_to_blocks
    edges = []
    for rect in page.rects:
        w, h = rect['width'], rect['height']
        if min(w, h) > 3 or max(w, h) < 5 or min(w, h) <= 0:
            continue
        vertical = h > w
        x, y = (rect['x0']+rect['x1'])/2, (rect['top']+rect['bottom'])/2
        edges.append(dict(object_type='line', x0=x if vertical else rect['x0'],
                          x1=x if vertical else rect['x1'],
                          top=rect['top'] if vertical else y,
                          bottom=rect['bottom'] if vertical else y,
                          width=0 if vertical else w, height=h if vertical else 0))
    if len(edges) < 8:
        return None
    detected = page.find_tables(dict(vertical_strategy='explicit', horizontal_strategy='explicit',
        explicit_vertical_lines=edges, explicit_horizontal_lines=edges,
        snap_tolerance=1.5, join_tolerance=3, intersection_tolerance=3))
    detected = [t for t in detected if len(t.columns) >= 2]
    parents = {}
    for i, inner in enumerate(detected):
        possible = [j for j, outer in enumerate(detected) if i != j
                    and enclosed(inner.bbox, outer.bbox, -.5)]
        if possible:
            parents[i] = min(possible, key=lambda j: (detected[j].bbox[2]-detected[j].bbox[0])*(detected[j].bbox[3]-detected[j].bbox[1]))
    rotated = any(not c.get('upright', True) for c in page.chars)
    if not parents and not rotated:
        return None
    def inside(char, bounds):
        return bounds[0] <= (char['x0']+char['x1'])/2 < bounds[2] and bounds[1] <= (char['top']+char['bottom'])/2 < bounds[3]
    def build(index, depth=0):
        if depth > 3:
            raise Rejected('Nested table depth exceeds limit.')
        child_ids = [i for i, parent in parents.items() if parent == index]
        # Exclude child glyphs from parent extraction; place them exactly once below.
        filtered = [{**w, 'chars':[c for c in w.get('chars', []) if not any(inside(c, detected[k].bbox) for k in child_ids)]} for w in words]
        candidates = native_tables(page, filtered, [detected[index]])
        if len(candidates) != 1:
            raise Rejected('Incomplete complex native table.')
        table = candidates[0]
        for child in child_ids:
            if sum(enclosed(detected[child].bbox, c['bbox']) for c in table['cells']) != 1:
                raise Rejected('Nested grid has no unique owning cell.')
        for cell in table['cells']:
            # extract_words deliberately drops whitespace glyphs. Read the
            # original cell glyphs so explicit spaces survive rotation too.
            chars = [c for c in page.chars if inside(c, cell['bbox'])
                     and not any(inside(c, detected[k].bbox) for k in child_ids)]
            chars = visible_spaces(chars)
            from pdfplumber.utils import extract_text
            cell['text'] = extract_text(chars, keep_blank_chars=True,
                                       x_tolerance=2, y_tolerance=3) or ''
            turning = [c for c in chars if not c.get('upright', True)]
            if turning:
                if len(turning) != len(chars):
                    raise Rejected('Mixed cell text directions require review.')
                from pdfplumber.utils import extract_text
                positive = all(c.get('matrix', (1,0))[1] > 0 for c in chars)
                negative = all(c.get('matrix', (1,0))[1] < 0 for c in chars)
                if not positive and not negative:
                    raise Rejected('Mixed rotated cell text requires review.')
                cell['text'] = extract_text(chars, line_dir_rotated='ltr',
                    char_dir_rotated='btt' if positive else 'ttb', keep_blank_chars=True,
                    x_tolerance=2, y_tolerance=3)
                cell['direction'] = 'btLr' if positive else 'tbRl'
                # The matrix scale is not a font size; use glyph width on rotated baselines.
                cell['size'] = median(c['x1']-c['x0'] for c in chars)
            children = [k for k in child_ids if enclosed(detected[k].bbox, cell['bbox'])]
            if children:
                parts = []
                from pdfplumber.utils import extract_words
                paras = words_to_blocks(extract_words(chars, return_chars=True, x_tolerance=2, y_tolerance=3),page.width,page.height,merge_paragraphs=False)
                parts.extend(paras)
                parts.extend(build(k, depth+1) for k in children)
                parts.sort(key=lambda b:(b['bbox'][1], b['bbox'][0]))
                for n, part in enumerate(parts):part['id'] = f'ruled-{index}-{cell["row"]}-{cell["col"]}-{n}-{depth}'
                cell['text'], cell['content'] = '', parts
        if any(c.get('direction') for c in table['cells']):
            ys = sorted(set(round(v,1) for c in detected[index].cells for v in (c[1],c[3])))
            if len(ys)-1 == table['rows']:
                table['row_heights'] = [b-a for a,b in zip(ys,ys[1:])]
        return table
    try:
        result = [build(i) for i in range(len(detected)) if i not in parents]
    except Rejected as error:
        if str(error) in ('Mixed cell text directions require review.',
                          'Mixed rotated cell text requires review.'):
            # This optional path only models one direction per cell. Leave
            # mixed-direction pages to the existing validated native/OCR route.
            return None
        raise
    # Do not accept intersecting peer grids. Nested grids have already been attached.
    for i,a in enumerate(result):
        for b in result[i+1:]:
            x,y=a['bbox'],b['bbox']
            if min(x[2],y[2])-max(x[0],y[0])>1 and min(x[3],y[3])-max(x[1],y[1])>1:
                raise Rejected('Overlapping complex native grids.')
    if rotated:
        attach_row_labels(result, words, page)
    return result


def attach_row_labels(tables, words, page):
    """Attach a narrow, consistently aligned label band; never absorb page prose."""
    from layout import words_to_blocks
    for table in tables:
        left, top, right, bottom = table['bbox']
        # A total band may omit the rule around its first value. Reuse an
        # aligned preceding grid only when every remaining boundary agrees.
        if table['rows'] == 1:
            above = [t for t in tables if t is not table and t['rows'] > 1
                     and 0 <= top-t['bbox'][3] <= 40 and abs(t['bbox'][2]-right) < 1]
            if above:
                reference = max(above, key=lambda t:t['bbox'][3])
                xs = [reference['bbox'][0]]
                for width in reference['widths']: xs.append(xs[-1]+width)
                start = min(range(len(xs)), key=lambda i:abs(xs[i]-left))
                own = [left]
                for width in table['widths']: own.append(own[-1]+width)
                if (0 < start <= 2 and len(own) == len(xs)-start
                        and all(abs(a-b) < 1 for a,b in zip(own,xs[start:]))):
                    from pdfplumber.utils import extract_text
                    added=[]
                    for col in range(start):
                        chars=[c for w in words for c in w.get('chars',[])
                               if xs[col] <= (c['x0']+c['x1'])/2 < xs[col+1]
                               and top <= (c['top']+c['bottom'])/2 < bottom]
                        added.append(dict(row=0,col=col,rowspan=1,colspan=1,
                            text=extract_text(chars) or '',size=median(c['size'] for c in chars) if chars else 8,
                            bbox=[xs[col],top,xs[col+1],bottom],header=False))
                    if all(c['text'] for c in added):
                        for cell in table['cells']:cell['col']+=start
                        table['cells'].extend(added)
                        table['cols']+=start
                        table['widths']=reference['widths'][:start]+table['widths']
                        table['bbox'][0]=xs[0]
                        continue
        outside = [w for w in words if w['x1'] <= left+1
                   and w['x0'] >= left-120 and top <= (w['top']+w['bottom'])/2 < bottom]
        labels = words_to_blocks(outside, page.width, page.height, merge_paragraphs=False)
        if not labels or any(len(p['text']) > 60 for p in labels):
            continue
        if table['rows'] > 1 and len(labels) < 4:
            continue
        if max(p['bbox'][0] for p in labels)-min(p['bbox'][0] for p in labels) > 20:
            continue
        boundaries = {}
        for c in table['cells']:
            boundaries[c['row']] = c['bbox'][1]
            boundaries[c['row']+c['rowspan']] = c['bbox'][3]
        if len(boundaries) != table['rows']+1:
            continue
        assigned = {}
        for label in labels:
            y = (label['bbox'][1]+label['bbox'][3])/2
            row = next((i for i in range(table['rows']) if boundaries[i] <= y < boundaries[i+1]), None)
            if row is None or row in assigned:
                break
            assigned[row] = label
        else:
            if table['cols'] >= 64:
                continue
            new_left = min(p['bbox'][0] for p in labels)
            for c in table['cells']:c['col'] += 1
            for row in range(table['rows']):
                label = assigned.get(row, {})
                table['cells'].append(dict(row=row,col=0,rowspan=1,colspan=1,
                    text=label.get('text',''),size=label.get('size',8),font=label.get('font','Arial'),
                    bbox=[new_left,boundaries[row],left,boundaries[row+1]],header=False))
            table['cols'] += 1
            table['widths'].insert(0, left-new_left)
            table['bbox'][0] = new_left
