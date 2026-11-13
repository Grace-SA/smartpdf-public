"""Recover only fully closed, source-backed, full-width section spans.

Native text-layer geometry is not proof of visibility under arbitrary clipping,
transparent text or vector occlusion. Existing words and cell bboxes are retained.
"""

import itertools
from copy import deepcopy
from statistics import median

from layout_native_order import _box, _finite, _geometry, _inside, _overlap
from layout_tables import model_box, physical_page, visible_box
from pdfplumber.utils import cluster_list, extract_text


def recover(item, page):
    try:
        return _recover(item, page)
    except (
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        OverflowError,
        ZeroDivisionError,
        AttributeError,
    ):
        return item


def _covered(edges, horizontal, position, start, end):
    intervals = []
    for edge in edges:
        b = _geometry(edge)
        fixed = (b[1] + b[3]) / 2 if horizontal else (b[0] + b[2]) / 2
        thickness = abs(b[3] - b[1]) if horizontal else abs(b[2] - b[0])
        if thickness <= 1.5 and abs(fixed - position) <= 1:
            intervals.append((b[0], b[2]) if horizontal else (b[1], b[3]))
    cursor = start
    for lo, hi in sorted(intervals):
        if hi < cursor:
            continue
        if lo > cursor + 1:
            break
        cursor = max(cursor, hi)
    return cursor >= end - 1


def _recover(item, page):
    if getattr(page, "rotation", 0):
        return item
    data = item["data"]
    cells = data["table_cells"]
    rows, cols = data["num_rows"], data["num_cols"]
    if (
        type(rows) is not int
        or type(cols) is not int
        or not 5 <= rows <= 300
        or not 3 <= cols <= 30
        or not isinstance(cells, list)
        or len(cells) > rows * cols
    ):
        return item
    occupied = {}
    boxes = {}
    for i, cell in enumerate(cells):
        keys = (
            "start_row_offset_idx",
            "end_row_offset_idx",
            "start_col_offset_idx",
            "end_col_offset_idx",
            "row_span",
            "col_span",
        )
        if (
            not isinstance(cell, dict)
            or any(type(cell.get(k)) is not int for k in keys)
            or not isinstance(cell.get("text"), str)
            or len(cell["text"]) > 2000
        ):
            return item
        r, er, c, ec, rs, cs = (cell[k] for k in keys)
        if not (
            0 <= r < er <= rows
            and 0 <= c < ec <= cols
            and rs == er - r
            and cs == ec - c
        ):
            return item
        for y in range(r, er):
            for x in range(c, ec):
                if (y, x) in occupied:
                    return item
                occupied[y, x] = i
        b = model_box(cell["bbox"], page)
        if not _box(b):
            return item
        boxes[i] = b
    candidates = {}
    for i, cell in enumerate(cells):
        if (
            cell["start_col_offset_idx"] != 0
            or cell["col_span"] != 1
            or cell["row_span"] != 1
            or not cell["text"].strip()
            or cell.get("column_header")
        ):
            continue
        row = cell["start_row_offset_idx"]
        covered = {occupied[row, c] for c in range(cols) if (row, c) in occupied}
        if any(
            j != i and (cells[j]["text"].strip() or cells[j]["row_span"] != 1)
            for j in covered
        ):
            continue
        candidates[i] = covered
    if not candidates:
        return item
    view = visible_box(page)
    if not _box(view):
        return item
    chars = page.chars
    if len(chars) > 50000 or any(
        not _box(_geometry(c)) or not isinstance(c.get("text"), str) for c in chars
    ):
        return item
    obstacles = []
    for objects in (page.annots, getattr(page, "images", [])):
        if not isinstance(objects, list) or len(objects) > 1000:
            return item
        for obj in objects:
            b = _geometry(obj)
            if not _box(b):
                return item
            obstacles.append(b)
    anchors = []
    for col in range(cols):
        values = [
            boxes[i][0]
            for i, c in enumerate(cells)
            if c["start_col_offset_idx"] == col
            and c["row_span"] == c["col_span"] == 1
            and c["text"].strip()
            and not c.get("column_header")
        ]
        if len(values) < 3:
            return item
        anchors.append(median(values))
    if any(b - a < 5 for a, b in itertools.pairwise(anchors)):
        return item
    native = physical_page(page)
    edges = native.edges
    if len(edges) > 5000:
        return item
    horizontal, vertical = [], []
    for edge in edges:
        b = _geometry(edge)
        if not all(_finite(v) for v in b) or b[0] > b[2] + 1e-7 or b[1] > b[3] + 1e-7:
            return item
        if edge.get("orientation") == "h":
            horizontal.append(b[1])
        elif edge.get("orientation") == "v":
            vertical.append(b[0])
        else:
            return item
    # Bound intersection work before invoking TableFinder. Use smaller clustering
    # tolerance than its default snapping, conservatively overcounting levels.
    if len(cluster_list(horizontal, 0.5)) * len(cluster_list(vertical, 0.5)) > 10000:
        return item
    tables = native.find_tables()
    if len(tables) > 100 or sum(len(t.cells) for t in tables) > 10000:
        return item
    if sum(len(t.cells) for t in tables) * len(cells) > 1_000_000:
        return item
    physical = []
    for table in tables:
        if not _box(table.bbox) or any(not _box(b) for b in table.cells):
            return item
        # Text starts do not establish a full column's extent. Independently
        # recover each column's physical range from >=3 populated body cells.
        ranges = []
        for col in range(cols):
            evidence = []
            source_cells = set()
            for i, cell in enumerate(cells):
                if (
                    cell["start_col_offset_idx"] != col
                    or cell["col_span"] != 1
                    or cell["row_span"] != 1
                    or not cell["text"].strip()
                    or cell.get("column_header")
                ):
                    continue
                matches = [
                    b
                    for b in table.cells
                    if _inside(boxes[i], b)
                    and sum(b[0] < x < b[2] for x in anchors) == 1
                    and b[0] < anchors[col] < b[2]
                ]
                if len(matches) == 1:
                    source_cells.add(tuple(matches[0]))
                    evidence.append((matches[0][0], matches[0][2]))
            if (
                len(source_cells) < 3
                or max(e[0] for e in evidence) - min(e[0] for e in evidence) > 1
                or max(e[1] for e in evidence) - min(e[1] for e in evidence) > 1
            ):
                break
            ranges.append(
                (median(e[0] for e in evidence), median(e[1] for e in evidence))
            )
        if len(ranges) != cols or any(
            abs(a[1] - b[0]) > 1 for a, b in itertools.pairwise(ranges)
        ):
            continue
        left, right = ranges[0][0], ranges[-1][1]
        if abs(left - table.bbox[0]) > 1 or abs(right - table.bbox[2]) > 1:
            continue
        for b in table.cells:
            if abs(b[0] - left) <= 1 and abs(b[2] - right) <= 1:
                physical.append(b)
    if len(physical) > 120:
        return item
    updates = {}
    remove = set()
    for i, covered in candidates.items():
        cell = cells[i]
        matches = [b for b in physical if _inside(boxes[i], b)]
        if len(matches) != 1:
            continue
        b = matches[0]
        if not _inside(b, view) or any(_overlap(o, b) for o in obstacles):
            continue
        glyphs = [g for g in chars if _overlap(_geometry(g), b)]
        if (
            not glyphs
            or len(glyphs) > 1000
            or any(not _inside(_geometry(g), b) for g in glyphs)
        ):
            continue
        if extract_text(glyphs).split() != cell["text"].split():
            continue
        # A physical rectangle cannot claim a second model row's glyph box.
        if any(
            j not in covered and c["text"].strip() and _overlap(boxes[j], b)
            for j, c in enumerate(cells)
        ):
            continue
        if not all(
            _covered(edges, h, p, start, end)
            for h, p, start, end in [
                (True, b[1], b[0], b[2]),
                (True, b[3], b[0], b[2]),
                (False, b[0], b[1], b[3]),
                (False, b[2], b[1], b[3]),
            ]
        ):
            continue
        if any(
            abs(e["x1"] - e["x0"]) <= 1.5
            and b[0] + 0.6 < e["x0"] < b[2] - 0.6
            and min(e["bottom"], b[3] - 1) - max(e["top"], b[1] + 1) > 1
            for e in edges
        ):
            continue
        updates[i] = cols
        remove.update(covered - {i})
    if not updates:
        return item
    result = deepcopy(item)
    for i in updates:
        result["data"]["table_cells"][i]["col_span"] = cols
        result["data"]["table_cells"][i]["end_col_offset_idx"] = cols
    result["data"]["table_cells"] = [
        c for i, c in enumerate(result["data"]["table_cells"]) if i not in remove
    ]
    return result
