"""Keep proven static form labels, values and checkbox crops on the same line."""


def inline_rows(blocks):
    if not any(b.get('static_form') for b in blocks):
        return blocks
    rows = []
    for block in sorted(blocks, key=lambda b: (b['bbox'][1], b['bbox'][0])):
        if block['kind'] in ('header', 'footer'):
            rows.append([block])
            continue
        left, top, right, bottom = block['bbox']
        matched = None
        for row in reversed(rows[-4:]):
            anchor = row[0]
            a, t, r, b = anchor['bbox']
            if (anchor['kind'] not in ('header', 'footer') and bottom-top >= 5
                    and b-t >= 5 and min(bottom, b)-max(top, t) >= .5*min(bottom-top,b-t)
                    and all(right <= item['bbox'][0]+1 or left >= item['bbox'][2]-1 for item in row)):
                matched = row
                break
        if matched is None:
            rows.append([block])
        else:
            matched.append(block)
    result = []
    for row in rows:
        row.sort(key=lambda b: b['bbox'][0])
        if len(row) == 1:
            result.extend(row)
        else:
            result.append(dict(kind='form_row', items=row, bbox=[
                min(b['bbox'][0] for b in row), min(b['bbox'][1] for b in row),
                max(b['bbox'][2] for b in row), max(b['bbox'][3] for b in row)]))
    return result
