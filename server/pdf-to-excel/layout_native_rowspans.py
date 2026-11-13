"""Restore one blank header tier only from a closed native ruled cell.

Existing text is moved, never inferred from annotations or expected labels.
Model row count and all body cells remain unchanged.
"""

import itertools
import math
from copy import deepcopy
from numbers import Real
from statistics import median

from layout_tables import model_box, physical_page, visible_box
from pdfplumber.utils import extract_text


def _compact(text):
    return "".join(text.split())


def _valid_box(box):
    return (
        isinstance(box, (list, tuple))
        and len(box) == 4
        and all(isinstance(v, Real) and math.isfinite(v) for v in box)
        and box[0] < box[2]
        and box[1] < box[3]
    )


def recover(item, page):
    # Optional structural recovery must not break an otherwise usable export
    # when native geometry or annotation decoding is malformed.
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
    cells = data["table_cells"]
    cols, rows = data["num_cols"], data["num_rows"]
    if (
        not isinstance(cols, int)
        or isinstance(cols, bool)
        or not isinstance(rows, int)
        or isinstance(rows, bool)
        or not isinstance(cells, list)
        or not 3 <= cols <= 30
        or not 5 <= rows <= 300
        or len(cells) > rows * cols
    ):
        return item
    occupied = {}
    for c in cells:
        if (
            not isinstance(c, dict)
            or not isinstance(c.get("text"), str)
            or any(
                not isinstance(c.get(k), int) or isinstance(c.get(k), bool)
                for k in (
                    "start_row_offset_idx",
                    "end_row_offset_idx",
                    "start_col_offset_idx",
                    "end_col_offset_idx",
                    "row_span",
                    "col_span",
                )
            )
        ):
            return item
        r, er, col, ec = (
            c[k]
            for k in (
                "start_row_offset_idx",
                "end_row_offset_idx",
                "start_col_offset_idx",
                "end_col_offset_idx",
            )
        )
        if not (
            0 <= r < er <= rows
            and 0 <= col < ec <= cols
            and c["row_span"] == er - r
            and c["col_span"] == ec - col
        ):
            return item
        for slot in ((y, x) for y in range(r, er) for x in range(col, ec)):
            if slot in occupied:
                return item
            occupied[slot] = c
    end = max(
        (c["end_row_offset_idx"] for c in cells if c.get("column_header")), default=0
    )
    if not 2 <= end <= 4:
        return item
    view = visible_box(page)
    table_box = model_box(item["prov"][0]["bbox"], page)
    if (
        not _valid_box(view)
        or not _valid_box(table_box)
        or not (
            view[0] <= table_box[0] < table_box[2] <= view[2]
            and view[1] <= table_box[1] < table_box[3] <= view[3]
        )
    ):
        return item
    candidates = [
        c
        for c in cells
        if c.get("column_header")
        and c["start_row_offset_idx"] == end - 1
        and c["row_span"] == c["col_span"] == 1
        and c["text"].strip()
        and "\n" not in c["text"]
        and "\r" not in c["text"]
    ]
    if not candidates:
        return item
    chars = [c for c in page.chars if c.get("text", "").strip()]
    if len(chars) > 50000 or any(
        not all(
            isinstance(c.get(k), (int, float)) and math.isfinite(c[k])
            for k in ("x0", "x1", "top", "bottom")
        )
        for c in chars
    ):
        return item

    def source(cell, bounds=None):
        if not cell.get("bbox"):
            return None
        b = bounds if bounds is not None else model_box(cell["bbox"], page)
        if not _valid_box(b):
            return None
        glyphs = [
            c
            for c in chars
            if b[0] - 0.1 <= (c["x0"] + c["x1"]) / 2 <= b[2] + 0.1
            and b[1] - 0.5 <= (c["top"] + c["bottom"]) / 2 <= b[3] + 0.5
        ]
        if not glyphs or any(
            not c.get("upright")
            or not (
                view[0] <= c["x0"] < c["x1"] <= view[2]
                and view[1] <= c["top"] < c["bottom"] <= view[3]
            )
            or not c.get("matrix")
            or len(c["matrix"]) != 6
            or not all(math.isfinite(v) for v in c["matrix"])
            or c["matrix"][0] <= 0
            or c["matrix"][3] <= 0
            or abs(c["matrix"][1]) > 0.001
            or abs(c["matrix"][2]) > 0.001
            for c in glyphs
        ):
            return None
        if max(c["top"] for c in glyphs) - min(c["top"] for c in glyphs) > 1:
            return None
        if _compact(extract_text(glyphs, x_tolerance=1.5, y_tolerance=2)) != _compact(
            cell["text"]
        ):
            return None
        return glyphs

    anchors = []
    for col in range(cols):
        boxes = [
            model_box(c["bbox"], page)
            for c in cells
            if c["start_row_offset_idx"] >= end
            and c["start_col_offset_idx"] == col
            and c["col_span"] == 1
            and c.get("bbox")
            and c["text"].strip()
        ]
        if len(boxes) < 3 or any(not _valid_box(b) for b in boxes):
            return item
        anchors.append(median((b[0] + b[2]) / 2 for b in boxes))
    if any(b - a < 5 for a, b in itertools.pairwise(anchors)):
        return item
    annotations = getattr(page, "annots", [])
    if not isinstance(annotations, list) or any(
        not isinstance(a, dict)
        or not _valid_box([a.get("x0"), a.get("top"), a.get("x1"), a.get("bottom")])
        for a in annotations
    ):
        return item
    physical = physical_page(page)
    edges = physical.edges
    if len(edges) > 800 or any(
        not isinstance(e, dict)
        or not all(
            isinstance(e.get(k), Real) and math.isfinite(e[k])
            for k in ("x0", "x1", "top", "bottom")
        )
        or e["x0"] > e["x1"]
        or e["top"] > e["bottom"]
        for e in edges
    ):
        return item
    native = physical.find_tables()
    if sum(len(t.cells) for t in native) > 4000 or any(
        not _valid_box(b) for t in native for b in t.cells
    ):
        return item
    changes = {}
    remove = set()
    for cell in candidates:
        r, col = cell["start_row_offset_idx"], cell["start_col_offset_idx"]
        above = occupied.get((r - 1, col))
        if above is not None and (
            above["text"].strip() or above["row_span"] != 1 or above["col_span"] != 1
        ):
            continue
        glyphs = source(cell)
        if not glyphs:
            continue
        matches = []
        for table in native:
            for box in table.cells:
                if not (
                    view[0] <= box[0] < box[2] <= view[2]
                    and view[1] <= box[1] < box[3] <= view[3]
                ):
                    continue
                if [i for i, x in enumerate(anchors) if box[0] < x < box[2]] != [col]:
                    continue
                if not all(
                    box[0] <= c["x0"] < c["x1"] <= box[2]
                    and box[1] <= c["top"] < c["bottom"] <= box[3]
                    for c in glyphs
                ):
                    continue
                if any(
                    e.get("orientation") == "h"
                    and box[1] + 0.5 < e["top"] < box[3] - 0.5
                    and min(e["x1"], box[2]) - max(e["x0"], box[0]) > 1
                    for e in edges
                ):
                    continue
                # Appearance streams may draw text even with empty/missing
                # Contents. No overlapping annotation is native glyph proof.
                if any(
                    a["x0"] < box[2]
                    and a["x1"] > box[0]
                    and a["top"] < box[3]
                    and a["bottom"] > box[1]
                    for a in annotations
                ):
                    continue
                whole = source(cell, box)
                if not whole or {id(c) for c in whole} != {id(c) for c in glyphs}:
                    continue
                upper = [
                    source(c)
                    for c in cells
                    if c.get("column_header")
                    and c["start_row_offset_idx"] == r - 1
                    and c["end_row_offset_idx"] == r
                    and c["text"].strip()
                ]
                upper = [g for g in upper if g]
                if len(upper) < 2:
                    continue
                ys = [median((c["top"] + c["bottom"]) / 2 for c in g) for g in upper]
                if max(ys) - min(ys) > 2 or not box[1] < min(ys) < max(
                    c["top"] for c in glyphs
                ):
                    continue
                # Adjacent physical cells prove a real header tier separator;
                # the candidate's single closed rectangle proves its absence here.
                splits = {
                    b[3]
                    for b in table.cells
                    if abs(b[1] - box[1]) <= 0.5 and box[1] + 3 < b[3] < box[3] - 3
                }
                splits = {
                    y
                    for y in splits
                    if max(ys) < y < min(c["top"] for c in glyphs)
                    and sum(
                        abs(b[1] - box[1]) <= 0.5 and abs(b[3] - y) <= 0.5
                        for b in table.cells
                    )
                    >= 2
                }
                if len(splits) != 1:
                    continue
                earlier = [
                    source(c)
                    for c in cells
                    if c.get("column_header")
                    and c["end_row_offset_idx"] <= r - 1
                    and c["text"].strip()
                ]
                if any(
                    g and max(c["bottom"] for c in g) > box[1] + 0.5 for g in earlier
                ):
                    continue
                matches.append(box)
        if len(matches) != 1:
            continue
        changes[id(cell)] = dict(cell, start_row_offset_idx=r - 1, row_span=2)
        if above is not None:
            remove.add(id(above))
    if not changes:
        return item
    out = deepcopy(item)
    out["data"]["table_cells"] = [
        deepcopy(changes.get(id(c), c)) for c in cells if id(c) not in remove
    ]
    return out
