"""Recover a split title only when the PDF independently proves a spanning cell."""
import copy
import collections
import re

from lxml import etree as E

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
N = {'w': W}


def tag(name):
    return '{' + W + '}' + name


def key(text):
    return re.sub(r'\s+', '', text)


def source_titles(page):
    """Small decorative edge strips are allowed; substantive split cells are not."""
    titles = []
    phrases = {}
    tables = page.find_tables()
    if len(tables) > 128:
        return {}
    for table in tables:
        if len(table.rows) < 2 or table.bbox[2] - table.bbox[0] < 100:
            continue
        first = table.extract()[0]
        occupied = [i for i, value in enumerate(first) if value and value.strip()]
        if len(occupied) != 1:
            continue
        i = occupied[0]
        rect = table.rows[0].cells[i]
        value = first[i]
        if (rect is None or len(value.split()) < 5 or any(c.isdigit() for c in value)
                or rect[0] - table.bbox[0] > 6 or table.bbox[2] - rect[2] > 6):
            continue
        titles.append(key(value))
        phrases[key(value)] = " ".join(value.split())
    counts = collections.Counter(titles)
    return {value: phrases[value] for value, count in counts.items() if count == 1}


def restore_titles(body, verified):
    if not isinstance(verified, dict):
        return 0
    candidates = []
    for table in body.iter(tag('tbl')):
        rows = table.findall(tag('tr'))
        if len(rows) < 2:
            continue
        row = rows[0]
        cells = row.findall(tag('tc'))
        if len(cells) < 3:
            continue
        value = key(''.join(row.xpath('.//w:t/text()', namespaces=N)))
        if value not in verified:
            continue
        # The merge inserts spaces between nonempty paragraphs. Require those
        # exact word boundaries in the source, not merely the same characters.
        chunks = [''.join(p.xpath('.//w:t/text()', namespaces=N))
                  for cell in cells for p in cell.findall(tag('p'))]
        if ' '.join(' '.join(chunks).split()) != verified[value]:
            continue
        # Explicitly absent internal borders and identical shading are required.
        fills = [c.find('w:tcPr/w:shd', N) for c in cells]
        if any(f is None for f in fills) or len({E.tostring(f) for f in fills}) != 1:
            continue
        if any(c.find('w:tcPr/w:vMerge', N) is not None or c.find('w:tcPr/w:gridSpan', N) is not None for c in cells):
            continue
        if any(c.xpath('.//w:drawing|.//w:fldChar|.//w:bookmarkStart|.//w:bookmarkEnd', namespaces=N) for c in cells):
            continue
        edges = [(cells[i], 'right') for i in range(len(cells)-1)] + [(cells[i], 'left') for i in range(1, len(cells))]
        if any((edge := c.find('w:tcPr/w:tcBorders/w:' + side, N)) is None or edge.get(tag('val')) not in ('nil', 'none') for c, side in edges):
            continue
        if len(cells) != len(table.findall('w:tblGrid/w:gridCol', N)):
            continue
        candidates.append((value, row, cells))
    counts = collections.Counter(value for value, _, _ in candidates)
    repaired = 0
    for value, row, cells in candidates:
        if counts[value] != 1:
            continue
        first = cells[0]
        props = first.find(tag('tcPr'))
        widths = [c.find('w:tcPr/w:tcW', N) for c in cells]
        if any(width is None or width.get(tag('type')) != 'dxa' for width in widths):
            continue
        total = sum(int(width.get(tag('w'))) for width in widths)
        borders = props.find(tag('tcBorders'))
        last_right = cells[-1].find('w:tcPr/w:tcBorders/w:right', N)
        if last_right is not None:
            old_right = borders.find(tag('right'))
            if old_right is not None:
                borders.remove(old_right)
            borders.append(copy.deepcopy(last_right))
        widths[0].set(tag('w'), str(total))
        span = E.Element(tag('gridSpan'))
        span.set(tag('val'), str(len(cells)))
        props.insert(list(props).index(widths[0]) + 1, span)
        paragraph = E.Element(tag('p'))
        pp = E.SubElement(paragraph, tag('pPr'))
        E.SubElement(pp, tag('jc')).set(tag('val'), 'center')
        spacing = E.SubElement(pp, tag('spacing'))
        for name, value in [('before', '0'), ('after', '0'), ('line', '240'), ('lineRule', 'auto')]:
            spacing.set(tag(name), value)
        for cell in cells:
            for old in cell.findall(tag('p')):
                if not ''.join(old.xpath('.//w:t/text()', namespaces=N)).strip():
                    continue
                if len(paragraph) > 1:
                    run = E.SubElement(paragraph, tag('r'))
                    space = E.SubElement(run, tag('t'))
                    space.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
                    space.text = ' '
                for child in list(old):
                    if child.tag != tag('pPr'):
                        paragraph.append(child)
        for child in list(first):
            if child is not props:
                first.remove(child)
        first.append(paragraph)
        for cell in cells[1:]:
            row.remove(cell)
        repaired += 1
    return repaired
