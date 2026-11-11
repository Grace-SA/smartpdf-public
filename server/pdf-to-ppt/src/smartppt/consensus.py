"""Spatial OCR consensus. Agreement is evidence, never a correctness guarantee.

Plain-text regions and strictly matched simple grids can authorize text edits.
Complex tables, formulas and images stay raster.
Each region must match the ordered text of its uniquely assigned Paddle lines;
page-wide character counts cannot authorize swapped columns or numbers.
"""
import math
from xml.etree import ElementTree
from .config import ConversionError
from .quality import normalized

TEXT_LABELS = {'text', 'title', 'caption', 'footnote', 'page-header', 'page-footer',
               'header', 'footer', 'paragraph', 'list', 'list_item'}


def line_bounds(line):
    points = line['polygon']
    return (min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points), max(p[1] for p in points))


def simple_grid_agreement(content, lines, indices):
    """Match a rectangular HTML grid to one spatially aligned OCR line per cell.

This approves positioned text, not an editable PowerPoint table. Merged/empty/
multiline cells and inconsistent columns require stronger geometry evidence.
"""
    if '<!DOCTYPE' in content.upper() or '<!ENTITY' in content.upper():
        return False
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError:
        return False
    if root.tag != 'table' or any(n.tag not in {'table','thead','tbody','tfoot','tr','td','th'} or n.attrib for n in root.iter()):
        return False
    rows = list(root.iter('tr'))
    cells = [[normalized(''.join(cell.itertext())) for cell in row if cell.tag in ('td','th')] for row in rows]
    if (not 1 <= len(cells) <= 100 or not 2 <= len(cells[0]) <= 20
            or any(len(row)!=len(cells[0]) or not all(row) for row in cells)
            or sum(map(len,cells)) != len(indices)):
        return False
    ordered = sorted(indices, key=lambda i: (sum(line_bounds(lines[i])[1::2])/2, line_bounds(lines[i])[0]))
    columns = len(cells[0]); positions = []
    for row, start in zip(cells, range(0,len(ordered),columns)):
        group = sorted(ordered[start:start+columns], key=lambda i:line_bounds(lines[i])[0])
        boxes = [line_bounds(lines[i]) for i in group]
        heights = [b-t for l,t,r,b in boxes]
        centers = [(t+b)/2 for l,t,r,b in boxes]
        if min(heights)<=0 or max(centers)-min(centers) > min(heights)*.5:
            return False
        if any(boxes[j][2]+2 >= boxes[j+1][0] for j in range(columns-1)):
            return False
        if [normalized(lines[i]['text']) for i in group] != row:
            return False
        positions.append(boxes)
    # Every inter-column gutter must remain open through the full block.
    return all(max(row[j][2] for row in positions)+2 < min(row[j+1][0] for row in positions)
               for j in range(columns-1))


def region_agreement(record, verifier):
    """Return a boolean for every line; malformed/unbound evidence fails closed."""
    if verifier.get('input_sha256') != record['input_sha256']:
        raise ConversionError('ocr_provenance_mismatch')
    if verifier.get('image_size') != record['image_size']:
        raise ConversionError('ocr_geometry_mismatch')
    lines = record['lines']; approved = [False] * len(lines)
    if verifier.get('capped') is not False:
        return approved
    blocks = verifier.get('blocks')
    if not isinstance(blocks, list) or len(blocks) > 3000:
        raise ConversionError('invalid_ocr_regions')
    width, height = record['image_size']; boxes = []
    units = verifier.get('coordinate_space')
    if units not in ('pixels', 'normalized-1000'):
        raise ConversionError('invalid_ocr_regions')
    for block in blocks:
        box = block.get('bbox', [])
        if (len(box) != 4 or any(type(x) not in (int, float) or not math.isfinite(x) for x in box)
                or not isinstance(block.get('content'), str) or len(block['content']) > 100000
                or not isinstance(block.get('label'), str) or block.get('page', 1) != 1):
            raise ConversionError('invalid_ocr_regions')
        if units == 'normalized-1000':
            box = [box[0]*width/1000, box[1]*height/1000, box[2]*width/1000, box[3]*height/1000]
        l, t, r, b = box
        if not (0 <= l < r <= width and 0 <= t < b <= height):
            raise ConversionError('invalid_ocr_regions')
        boxes.append(box)
    # Upstream may emit the same footer as both Text and Page-footer. Coalesce
    # only exactly coincident, identical plain text; conflicting overlaps veto.
    unique = []; unique_boxes = []; seen = set()
    for block, box in zip(blocks, boxes):
        key = (tuple(box), normalized(block['content']))
        if block['label'].lower() in TEXT_LABELS:
            if key in seen: continue
            seen.add(key)
        unique.append(block); unique_boxes.append(box)
    blocks, boxes = unique, unique_boxes
    assigned = [[] for _ in blocks]
    for index, line in enumerate(lines):
        l, t, r, b = line_bounds(line); cx, cy = (l+r)/2, (t+b)/2
        # All region types participate: overlapping table/figure regions veto edits.
        matches = [i for i, (x, y, xx, yy) in enumerate(boxes) if x <= cx <= xx and y <= cy <= yy]
        if len(matches) == 1:
            i = matches[0]; x, y, xx, yy = boxes[i]
            # Detectors have small edge discrepancies; disallow lines crossing columns.
            tolerance = max(3, (b-t)*.25)
            if l >= x-tolerance and r <= xx+tolerance and t >= y-tolerance and b <= yy+tolerance:
                assigned[i].append(index)
    for block, indices in zip(blocks, assigned):
        if not indices:
            continue
        if block['label'].lower() == 'table':
            if simple_grid_agreement(block['content'],lines,indices):
                for i in indices:approved[i]=True
            continue
        if block['label'].lower() not in TEXT_LABELS:continue
        indices.sort(key=lambda i: (line_bounds(lines[i])[1], line_bounds(lines[i])[0]))
        actual = ''.join(lines[i]['text'] for i in indices)
        if normalized(actual) and normalized(actual) == normalized(block['content']):
            for i in indices:
                approved[i] = True
    return approved


def erase_bounds(line):
    """Integer pixel bounds shared by erasure and its overlap safety check."""
    l, t, r, b = line_bounds(line)
    return math.floor(l)-1, math.floor(t)-1, math.ceil(r)+1, math.ceil(b)+1


def overlapping_lines(lines):
    """Any intersecting erase rectangles stay raster, including duplicate detections."""
    blocked = set(); boxes = [erase_bounds(line) for line in lines]
    for i, (l, t, r, b) in enumerate(boxes):
        for j in range(i):
            x, y, xx, yy = boxes[j]
            if min(r, xx) > max(l, x) and min(b, yy) > max(t, y):
                blocked.update((i, j))
    return blocked
