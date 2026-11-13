"""Conservatively join one wrapped native text-layer stub in a closed 2-row grid.

This proves glyph/crop/grid consistency, not visibility under arbitrary PDF
clipping, transparent text, render modes or vector occlusion.
"""

import itertools
from copy import deepcopy
from statistics import median

from layout_native_order import _box, _finite, _geometry, _inside, _overlap
from layout_tables import model_box, physical_page, visible_box
from pdfplumber.utils import extract_text


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


def _recover(item, page):
    if getattr(page, "rotation", 0):
        return item
    data = item["data"]
    rows, cols, cells = data["num_rows"], data["num_cols"], data["table_cells"]
    if (
        type(rows) is not int
        or rows != 3
        or type(cols) is not int
        or not 3 <= cols <= 30
        or not isinstance(cells, list)
        or not 2 * cols + 1 <= len(cells) <= 3 * cols
    ):
        return item
    indexed = {}
    for cell in cells:
        keys = (
            "start_row_offset_idx",
            "end_row_offset_idx",
            "start_col_offset_idx",
            "end_col_offset_idx",
            "row_span",
            "col_span",
        )
        if not isinstance(cell, dict) or any(
            type(cell.get(k)) is not int for k in keys
        ):
            return item
        r, er, c, ec, rs, cs = (cell[k] for k in keys)
        if not (
            0 <= r < er <= 3
            and 0 <= c < ec <= cols
            and er - r == rs == 1
            and ec - c == cs == 1
            and (r, c) not in indexed
            and isinstance(cell.get("text"), str)
            and len(cell["text"]) <= 1000
        ):
            return item
        indexed[r, c] = cell
    if (
        any((r, c) not in indexed for r in (0, 1) for c in range(cols))
        or (2, 0) not in indexed
    ):
        return item
    if any(c["text"].strip() for (r, col), c in indexed.items() if r == 2 and col != 0):
        return item
    first, second = indexed[1, 0], indexed[2, 0]
    if any(c.get("column_header") or c.get("row_section") for c in (first, second)):
        return item
    if any(
        not c["text"].strip()
        or not c["text"].isascii()
        or any(ch.isdigit() for ch in c["text"])
        for c in (first, second)
    ):
        return item
    view = visible_box(page)
    if not _box(view):
        return item
    chars = page.chars
    if len(chars) > 50000 or any(
        not _box(_geometry(c)) or not isinstance(c.get("text"), str) for c in chars
    ):
        return item
    native = physical_page(page)
    edges = native.edges
    if len(edges) > 800:
        return item
    for edge in edges:
        b = _geometry(edge)
        if not all(_finite(v) for v in b) or b[0] > b[2] + 1e-7 or b[1] > b[3] + 1e-7:
            return item
    tables = native.find_tables()
    if len(tables) > 100:
        return item
    source_box = model_box(item["prov"][0]["bbox"], page)
    if not _box(source_box):
        return item
    candidates = [t for t in tables if _overlap(t.bbox, source_box)]
    if len(candidates) != 1:
        return item
    table = candidates[0]
    if (
        not _box(table.bbox)
        or not _inside(table.bbox, view)
        or len(table.cells) != 2 * cols
    ):
        return item
    boxes = table.cells
    if any(not _box(b) for b in boxes):
        return item
    xs = sorted({v for b in boxes for v in (b[0], b[2])})
    ys = sorted({v for b in boxes for v in (b[1], b[3])})
    if len(xs) != cols + 1 or len(ys) != 3:
        return item
    expected = {
        (xs[c], ys[r], xs[c + 1], ys[r + 1]) for r in range(2) for c in range(cols)
    }
    if set(map(tuple, boxes)) != expected:
        return item
    # TableFinder may bridge gaps; require independent edge coverage of all grid
    # borders, allowing at most one point for thin-rule endpoint rounding.
    for horizontal, positions, start, end in (
        (True, ys, xs[0], xs[-1]),
        (False, xs, ys[0], ys[-1]),
    ):
        for position in positions:
            intervals = []
            for edge in edges:
                b = _geometry(edge)
                fixed = (b[1] + b[3]) / 2 if horizontal else (b[0] + b[2]) / 2
                thickness = abs(b[3] - b[1]) if horizontal else abs(b[2] - b[0])
                if thickness <= 1 and abs(fixed - position) <= 0.6:
                    intervals.append((b[0], b[2]) if horizontal else (b[1], b[3]))
            cursor = start
            for lo, hi in sorted(intervals):
                if hi < cursor:
                    continue
                if lo > cursor + 1:
                    break
                cursor = max(cursor, hi)
            if cursor < end - 1:
                return item
    # Even an incomplete rule inside a physical row makes joining ambiguous.
    for edge in edges:
        b = _geometry(edge)
        if (
            abs(b[3] - b[1]) <= 1
            and b[2] - b[0] > 1
            and b[0] < xs[-1]
            and b[2] > xs[0]
            and (
                ys[0] < (b[1] + b[3]) / 2 < ys[-1]
                and min(abs((b[1] + b[3]) / 2 - y) for y in ys) > 1
            )
        ):
            return item
    for objects in (page.annots, getattr(page, "images", [])):
        if not isinstance(objects, list) or len(objects) > 1000:
            return item
        for obj in objects:
            b = _geometry(obj)
            if not _box(b) or _overlap(b, table.bbox):
                return item
    if any(not _box(model_box(c["bbox"], page)) for c in cells):
        return item
    selected = {}
    for (r, c), cell in indexed.items():
        if not cell["text"].strip():
            continue
        box = (xs[c], ys[min(r, 1)], xs[c + 1], ys[min(r, 1) + 1])
        b = model_box(cell["bbox"], page)
        if not _box(b) or not _inside(b, box):
            return item
        glyphs = [
            g
            for g in chars
            if b[0] <= (g["x0"] + g["x1"]) / 2 <= b[2]
            and b[1] <= (g["top"] + g["bottom"]) / 2 <= b[3]
        ]
        if (
            not glyphs
            or len(glyphs) > 1000
            or any(not _inside(_geometry(g), box) for g in glyphs)
        ):
            return item
        if extract_text(glyphs).split() != cell["text"].split():
            return item
        selected[r, c] = glyphs
    for r in range(2):
        for c in range(cols):
            box = (xs[c], ys[r], xs[c + 1], ys[r + 1])
            full = [
                g for g in chars if g["text"].strip() and _overlap(_geometry(g), box)
            ]
            owned = selected.get((r, c), []) + (
                selected.get((2, 0), []) if (r, c) == (1, 0) else []
            )
            if {id(g) for g in full} != {id(g) for g in owned if g["text"].strip()}:
                return item
    lines = [selected[1, 0], selected[2, 0]]
    glyphs = list(itertools.chain.from_iterable(lines))
    sizes = [g.get("size") for g in glyphs]
    if any(not _finite(s) or not 6 <= s <= 24 for s in sizes):
        return item
    size = median(sizes)
    font = glyphs[0].get("fontname")
    if not isinstance(font, str) or not font.strip():
        return item
    for g in glyphs:
        m = g.get("matrix")
        if (
            not g.get("upright")
            or g.get("fontname") != font
            or abs(g["size"] - size) > 0.1
            or not isinstance(m, (tuple, list))
            or len(m) != 6
            or not all(_finite(v) for v in m)
            or m[0] <= 0
            or m[3] <= 0
            or abs(m[1]) > 0.001
            or abs(m[2]) > 0.001
        ):
            return item
    if abs(min(g["x0"] for g in lines[0]) - min(g["x0"] for g in lines[1])) > 1:
        return item
    if any(
        max(g["matrix"][5] for g in line) - min(g["matrix"][5] for g in line) > 0.5
        for line in lines
    ):
        return item
    gap = median(g["matrix"][5] for g in lines[0]) - median(
        g["matrix"][5] for g in lines[1]
    )
    if not 0.9 * size <= gap <= 1.8 * size or max(g["bottom"] for g in lines[0]) >= min(
        g["top"] for g in lines[1]
    ):
        return item
    result = deepcopy(item)
    target = result["data"]
    target["num_rows"] = 2
    target["table_cells"] = [
        c for c in target["table_cells"] if c["start_row_offset_idx"] != 2
    ]
    for cell in target["table_cells"]:
        if (cell["start_row_offset_idx"], cell["start_col_offset_idx"]) == (1, 0):
            cell["text"] = first["text"] + "\n" + second["text"]
            a, b = model_box(first["bbox"], page), model_box(second["bbox"], page)
            cell["bbox"] = {
                "l": min(a[0], b[0]) - view[0],
                "t": min(a[1], b[1]) - view[1],
                "r": max(a[2], b[2]) - view[0],
                "b": max(a[3], b[3]) - view[1],
                "coord_origin": "TOPLEFT",
            }
    return result
