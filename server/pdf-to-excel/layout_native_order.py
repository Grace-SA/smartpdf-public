"""Recover source line order in native headers and line breaks in section labels.

Only reorders an exact word multiset. No OCR, inferred words or value changes.
This optional recovery is deliberately conservative about glyph ownership.
"""

import itertools
import math
from collections import Counter
from copy import deepcopy
from numbers import Real
from statistics import median

from layout_tables import model_box, visible_box
from pdfplumber.utils import cluster_objects, extract_text


def _finite(value):
    return (
        isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value)
    )


def _box(box):
    return (
        isinstance(box, (tuple, list))
        and len(box) == 4
        and all(_finite(v) for v in box)
        and box[0] < box[2]
        and box[1] < box[3]
    )


def _overlap(a, b):
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def _inside(a, b, tolerance=0):
    return (
        b[0] - tolerance <= a[0] < a[2] <= b[2] + tolerance
        and b[1] - tolerance <= a[1] < a[3] <= b[3] + tolerance
    )


def _geometry(obj):
    return (obj["x0"], obj["top"], obj["x1"], obj["bottom"])


def recover(item, page):
    """Return original object on uncertain or malformed native evidence."""
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
    cells = item["data"]["table_cells"]
    if not isinstance(cells, list) or not 1 <= len(cells) <= 9000:
        return item
    data = item["data"]
    rows, cols = data.get("num_rows"), data.get("num_cols")
    if (
        type(rows) is not int
        or type(cols) is not int
        or not 1 <= rows <= 300
        or not 1 <= cols <= 30
        or len(cells) > rows * cols
    ):
        return item
    occupied = set()
    for cell in cells:
        if not isinstance(cell, dict) or not isinstance(cell.get("text"), str):
            return item
        keys = (
            "start_row_offset_idx",
            "end_row_offset_idx",
            "start_col_offset_idx",
            "end_col_offset_idx",
            "row_span",
            "col_span",
        )
        if any(type(cell.get(key)) is not int for key in keys):
            return item
        r, er, c, ec, rs, cs = (cell[key] for key in keys)
        if not (
            0 <= r < er <= rows
            and 0 <= c < ec <= cols
            and rs == er - r
            and cs == ec - c
        ):
            return item
        for row in range(r, er):
            for col in range(c, ec):
                if (row, col) in occupied:
                    return item
                occupied.add((row, col))
    view = visible_box(page)
    if not _box(view):
        return item
    boxes = [model_box(c["bbox"], page) for c in cells]
    if any(not _box(b) for b in boxes):
        return item
    raw = page.chars
    annotations = page.annots
    if len(raw) > 50000 or len(annotations) > 1000:
        return item
    if any(not isinstance(c.get("text"), str) or not _box(_geometry(c)) for c in raw):
        return item
    images = getattr(page, "images", [])
    if not isinstance(images, list) or len(images) > 1000:
        return item
    imageboxes = [_geometry(image) for image in images]
    if any(not _box(b) for b in imageboxes):
        return item
    annboxes = [_geometry(a) for a in annotations]
    if any(not _box(b) for b in annboxes):
        return item
    chars = [c for c in raw if c["text"].strip()]
    candidates = [
        i
        for i, c in enumerate(cells)
        if (c.get("column_header") is True or c.get("row_section") is True)
        and type(c.get("row_span")) is int
        and c.get("row_span") == 1
        and type(c.get("col_span")) is int
        and c.get("col_span") == 1
        and isinstance(c.get("text"), str)
        and 1 <= len(c["text"]) <= 1000
    ]
    if len(candidates) > 120:
        return item
    updates = {}
    for i in candidates:
        cell, b = cells[i], boxes[i]
        if not cell["text"].isascii() or not _inside(b, view):
            continue
        selected = [
            c
            for c in chars
            if b[0] <= (c["x0"] + c["x1"]) / 2 <= b[2]
            and b[1] <= (c["top"] + c["bottom"]) / 2 <= b[3]
        ]
        if not 2 <= len(selected) <= 200:
            continue
        sizes = [c.get("size") for c in selected]
        if any(not _finite(s) or not 6 <= s <= 24 for s in sizes):
            continue
        size = median(sizes)
        font = selected[0].get("fontname")
        if not isinstance(font, str) or not font:
            continue
        valid = True
        for c in selected:
            matrix = c.get("matrix")
            if (
                not c.get("upright")
                or abs(c["size"] - size) > 0.1
                or c.get("fontname") != font
                or not isinstance(matrix, (list, tuple))
                or len(matrix) != 6
                or not all(_finite(v) for v in matrix)
                or matrix[0] <= 0
                or matrix[3] <= 0
                or abs(matrix[1]) > 0.001
                or abs(matrix[2]) > 0.001
            ):
                valid = False
                break
        if not valid:
            continue
        tolerance = min(1.5, 0.15 * size)
        if any(
            not _inside(_geometry(c), view) or not _inside(_geometry(c), b, tolerance)
            for c in selected
        ):
            continue
        envelope = (
            min(c["x0"] for c in selected),
            min(c["top"] for c in selected),
            max(c["x1"] for c in selected),
            max(c["bottom"] for c in selected),
        )
        # Native characters over an image may be an invisible OCR text layer.
        # This is not a general proof of visibility under arbitrary PDF clipping.
        if any(_overlap(image, envelope) for image in imageboxes):
            continue
        # Check the whole evidence region, including the small metric tolerance.
        region = (
            min(b[0], envelope[0]),
            min(b[1], envelope[1]),
            max(b[2], envelope[2]),
            max(b[3], envelope[3]),
        )
        selected_ids = set(map(id, selected))
        if any(
            id(c) not in selected_ids and _overlap(_geometry(c), region) for c in chars
        ):
            continue
        if any(_overlap(a, region) for a in annboxes):
            continue
        # Any other model cell claiming even part of a selected glyph is ambiguous.
        if any(
            _overlap(other, _geometry(c))
            for j, other in enumerate(boxes)
            if j != i and _overlap(other, region)
            for c in selected
        ):
            continue
        lines = cluster_objects(selected, lambda c: c["matrix"][5], 1)
        lines.sort(key=lambda line: min(c["top"] for c in line))
        if not 2 <= len(lines) <= 3:
            continue
        if any(
            max(c["matrix"][5] for c in line) - min(c["matrix"][5] for c in line) > 0.5
            for line in lines
        ):
            continue
        if any(
            not 0.9 * size
            <= median(c["matrix"][5] for c in a) - median(c["matrix"][5] for c in z)
            <= 2.5 * size
            or max(c["bottom"] for c in a) >= min(c["top"] for c in z)
            for a, z in itertools.pairwise(lines)
        ):
            continue
        text = "\n".join(
            extract_text(line, x_tolerance=1.5, y_tolerance=1) for line in lines
        )
        if Counter(text.split()) != Counter(cell["text"].split()):
            continue
        if cell.get("row_section") is True:
            # A wrapped heading and nested group labels can share identical
            # geometry. Preserve source lines, but never infer another row or
            # reorder section words from geometry alone.
            if text.split() == cell["text"].split() and text != cell["text"]:
                updates[i] = text
        elif text.split() != cell["text"].split():
            # Preserve already-correct ordinary header whitespace.
            updates[i] = text
    if not updates:
        return item
    result = deepcopy(item)
    for i, text in updates.items():
        result["data"]["table_cells"][i]["text"] = text
    return result
