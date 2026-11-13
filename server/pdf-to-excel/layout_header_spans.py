"""Narrow a grouped heading when its source underline excludes a stub column."""

from copy import deepcopy
from statistics import median


def recover(item, page):
    from layout_tables import model_box, physical_page, visible_box, visible_glyphs
    from pdfplumber.utils import extract_text

    data = item["data"]
    cells = data["table_cells"]
    groups = [
        c
        for c in cells
        if c["start_row_offset_idx"] == 0
        and c["row_span"] == 1
        and c["col_span"] > 1
        and c.get("column_header")
        and c.get("bbox")
    ]
    if not 3 <= len(groups) <= 12 or not 5 <= data["num_cols"] <= 40:
        return item
    if any(not c.get("bbox") for c in cells if c["text"].strip()):
        return item
    anchors = {}
    for col in range(data["num_cols"]):
        boxes = [
            model_box(c["bbox"], page)
            for c in cells
            if c["start_row_offset_idx"] >= 2
            and c["col_span"] == 1
            and c["start_col_offset_idx"] == col
            and c["text"].strip()
        ]
        if len(boxes) < 3:
            return item
        anchors[col] = median((b[0] + b[2]) / 2 for b in boxes)
    if any(anchors[c] >= anchors[c + 1] for c in range(data["num_cols"] - 1)):
        return item
    changes = {}
    for group in groups:
        b = model_box(group["bbox"], page)
        # Only contract an existing span; no new heading text is inferred.
        candidates = set()
        for edge in physical_page(page).edges:
            if not (
                edge.get("orientation") == "h"
                and b[3] - 0.5 <= edge["top"] <= b[3] + 3
                and edge["x0"] <= b[0] + 1
                and edge["x1"] >= b[2] - 1
            ):
                continue
            covered = [c for c, x in anchors.items() if edge["x0"] <= x <= edge["x1"]]
            if len(covered) < 2 or covered != list(
                range(min(covered), max(covered) + 1)
            ):
                continue
            left, right = min(covered), max(covered) + 1
            old_left, old_right = (
                group["start_col_offset_idx"],
                group["end_col_offset_idx"],
            )
            if (
                old_left <= left < right <= old_right
                and right - left == group["col_span"] - 1
            ):
                candidates.add((left, right))
        if len(candidates) != 1:
            continue
        left, right = candidates.pop()
        children = [
            c
            for c in cells
            if c["start_row_offset_idx"] == 1
            and left <= c["start_col_offset_idx"] < right
        ]
        if len(children) != right - left or any(
            c["row_span"] != 1 or c["col_span"] != 1 or not c.get("column_header")
            for c in children
        ):
            continue
        changes[id(group)] = (left, right)
    if not changes:
        return item
    covered = set()
    for c in cells:
        if c["start_row_offset_idx"] != 0:
            continue
        left, right = changes.get(
            id(c), (c["start_col_offset_idx"], c["end_col_offset_idx"])
        )
        covered.update(range(left, right))
    stubs = [
        c
        for c in cells
        if c["start_row_offset_idx"] == 1
        and c["start_col_offset_idx"] not in covered
        and c["text"].strip()
    ]
    if not 2 <= len(stubs) <= 6 or any(
        c["row_span"] != 1
        or c["col_span"] != 1
        or not c.get("column_header")
        or len(c["text"].split()) > 3
        for c in stubs
    ):
        return item
    # Repeated short stubs have the same source text and baseline. A unique
    # unmatched label might instead belong to another header tier.
    canon = lambda text: "".join(text.split())
    if len({canon(c["text"]) for c in stubs}) != 1:
        return item
    boxes = [model_box(c["bbox"], page) for c in stubs]
    if max(b[1] for b in boxes) - min(b[1] for b in boxes) > 2:
        return item
    view = visible_box(page)
    glyphs = visible_glyphs(page.chars)
    for c in stubs + groups:
        b = model_box(c["bbox"], page)
        selected = [
            ch
            for ch in glyphs
            if b[0] - 0.5 <= (ch["x0"] + ch["x1"]) / 2 <= b[2] + 0.5
            and b[1] - 0.5 <= (ch["top"] + ch["bottom"]) / 2 <= b[3] + 0.5
            and view[0] <= ch["x0"] <= ch["x1"] <= view[2]
            and view[1] <= ch["top"] <= ch["bottom"] <= view[3]
        ]
        if not selected or canon(extract_text(selected)) != canon(c["text"]):
            return item
    result = deepcopy(item)
    for old, new in zip(cells, result["data"]["table_cells"]):
        if id(old) in changes:
            left, right = changes[id(old)]
            new.update(
                start_col_offset_idx=left,
                end_col_offset_idx=right,
                col_span=right - left,
            )
        if old in stubs:
            new.update(start_row_offset_idx=0, end_row_offset_idx=2, row_span=2)
    occupied = set()
    for c in result["data"]["table_cells"]:
        area = {
            (r, col)
            for r in range(c["start_row_offset_idx"], c["end_row_offset_idx"])
            for col in range(c["start_col_offset_idx"], c["end_col_offset_idx"])
        }
        if occupied & area:
            return item
        occupied.update(area)
    return result
