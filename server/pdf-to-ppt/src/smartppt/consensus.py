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
from .partial_consensus import partial_line_agreement

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
    # Compare cell centers in the table's own orientation. A clear slightly
    # skewed scan must satisfy the same row/column tolerances as an upright one.
    from statistics import median
    angles=[math.atan2(lines[i]['polygon'][1][1]-lines[i]['polygon'][0][1],
                       lines[i]['polygon'][1][0]-lines[i]['polygon'][0][0]) for i in indices]
    angle=median(angles)
    if abs(math.degrees(angle))>8 or any(abs(math.degrees(a-angle))>3 for a in angles):return False
    c,s=math.cos(angle),math.sin(angle)
    aligned={}
    for i in indices:
        points=[(x*c+y*s,-x*s+y*c) for x,y in lines[i]['polygon']]
        aligned[i]=(min(x for x,y in points),min(y for x,y in points),max(x for x,y in points),max(y for x,y in points))
    ordered = sorted(indices, key=lambda i: (sum(aligned[i][1::2])/2, aligned[i][0]))
    columns = len(cells[0]); positions = []
    for row, start in zip(cells, range(0,len(ordered),columns)):
        group = sorted(ordered[start:start+columns], key=lambda i:aligned[i][0])
        boxes = [aligned[i] for i in group]
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
    assigned = [[] for _ in blocks]; memberships=[]
    for index, line in enumerate(lines):
        l, t, r, b = line_bounds(line); cx, cy = (l+r)/2, (t+b)/2
        matches = [i for i, (x, y, xx, yy) in enumerate(boxes) if x <= cx <= xx and y <= cy <= yy]
        memberships.append(matches)
        for i in matches:
            x, y, xx, yy = boxes[i]
            tolerance = max(3, (b-t)*.25)
            if l >= x-tolerance and r <= xx+tolerance and t >= y-tolerance and b <= yy+tolerance:
                assigned[i].append(index)
    agreements=[]; exact=[]
    for block, indices in zip(blocks, assigned):
        accepted=set(); whole=False; label=block['label'].lower()
        if indices and label=='table':
            if simple_grid_agreement(block['content'],lines,indices):accepted.update(indices)
        elif indices and label in TEXT_LABELS:
            indices.sort(key=lambda i: (line_bounds(lines[i])[1], line_bounds(lines[i])[0]))
            actual=normalized(''.join(lines[i]['text'] for i in indices))
            whole=bool(actual) and actual==normalized(block['content'])
            if whole:accepted.update(indices)
            else:
                safe=partial_line_agreement([lines[i]['text'] for i in indices],block['content'])
                accepted.update(i for i,ok in zip(indices,safe) if ok)
        agreements.append(accepted);exact.append(whole)
    def contains(a,b):return a[0]<=b[0] and a[1]<=b[1] and a[2]>=b[2] and a[3]>=b[3]
    for line_index,matches in enumerate(memberships):
        if len(matches)==1:approved[line_index]=line_index in agreements[matches[0]]
        elif len(matches)>1:
            # Some layout models emit both a paragraph and its constituent
            # lines. Accept only nested plain regions, each independently an
            # exact match of every assigned line. Conflicting text, crossing
            # regions and any structural overlap still veto edits.
            plain=all(blocks[i]['label'].lower() in TEXT_LABELS and exact[i] and line_index in agreements[i] for i in matches)
            nested=all(contains(boxes[i],boxes[j]) or contains(boxes[j],boxes[i]) for n,i in enumerate(matches) for j in matches[n+1:])
            approved[line_index]=plain and nested

    return approved


def erase_bounds(line):
    """Integer pixel bounds shared by erasure and its overlap safety check."""
    l, t, r, b = line_bounds(line)
    return math.floor(l)-1, math.floor(t)-1, math.ceil(r)+1, math.ceil(b)+1


def overlapping_lines(lines,image=None):
    """Any intersecting erase rectangles stay raster, including duplicate detections."""
    blocked = set(); boxes = [erase_bounds(line) for line in lines]
    for i, (l, t, r, b) in enumerate(boxes):
        for j in range(i):
            x, y, xx, yy = boxes[j]
            if min(r, xx) > max(l, x) and min(b, yy) > max(t, y):
                if image is not None:
                    import numpy as np
                    pixels=np.asarray(image)
                    left,top,right,bottom=max(0,l,x),max(0,t,y),min(pixels.shape[1],r,xx),min(pixels.shape[0],b,yy)
                    shared=pixels[top:bottom,left:right].astype(float)
                    if shared.size:
                        paper=np.median(shared.reshape(-1,3),axis=0)
                        # Permit only entirely empty, uniformly light overlap.
                        # One dark pixel still vetoes both erase rectangles.
                        if paper.min()>=180 and np.max(np.abs(shared-paper))<=12:continue
                blocked.update((i, j))
    return blocked
