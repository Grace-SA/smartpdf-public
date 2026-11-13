"""Separate compressed section levels proven by repeated source hierarchy."""

from collections import Counter
from copy import deepcopy
from statistics import median
import math

from pdfplumber.utils import cluster_objects, extract_text
from layout_tables import model_box, local_box


def recover(item, page):
    data = item["data"]
    cells = data["table_cells"]
    if getattr(page, "rotation", 0) or not 2 <= data["num_cols"] <= 30:
        return item
    sections = [
        c
        for c in cells
        if c.get("row_section")
        and c.get("bbox")
        and c["start_col_offset_idx"] == 0
        and c["col_span"] == 1
        and c["row_span"] == 1
        and c["text"].strip()
    ]
    if len(sections) < 2:
        return item
    edits = []
    for cell in sections:
        row = cell["start_row_offset_idx"]
        if any(
            c is not cell
            and c["start_row_offset_idx"] <= row < c["end_row_offset_idx"]
            and (c["text"].strip() or c["row_span"] != 1)
            for c in cells
        ):
            continue
        b = model_box(cell["bbox"], page)
        if not all(math.isfinite(v) for v in b):
            continue
        chars = [
            c
            for c in page.chars
            if c["text"].strip()
            and b[0] - 1 <= (c["x0"] + c["x1"]) / 2 <= b[2] + 1
            and b[1] - 1 <= (c["top"] + c["bottom"]) / 2 <= b[3] + 1
        ]
        if not chars or any(not c.get("upright") for c in chars):
            continue
        height = median(c["bottom"] - c["top"] for c in chars)
        if not 4 <= height <= 30:
            continue
        groups = cluster_objects(
            chars, lambda c: (c["top"] + c["bottom"]) / 2, min(2, height / 4)
        )
        if len(groups) != 2:
            continue
        lines = [
            extract_text(group, x_tolerance=1.5, y_tolerance=2) for group in groups
        ]
        if " ".join(" ".join(lines).split()) != " ".join(cell["text"].split()):
            continue
        xs = [min(c["x0"] for c in group) for group in groups]
        ys = [median((c["top"] + c["bottom"]) / 2 for c in group) for group in groups]
        if xs[1] - xs[0] < height or not height * 0.8 < ys[1] - ys[0] < height * 2:
            continue
        # A later same-indent sibling with repeated child labels distinguishes
        # two hierarchy levels from an ordinary wrapped heading.
        later = sorted(
            (c for c in sections if c["start_row_offset_idx"] > row),
            key=lambda c: c["start_row_offset_idx"],
        )
        if not later:
            continue
        sibling = later[0]
        sb = model_box(sibling["bbox"], page)
        if abs(sb[0] - xs[1]) > height * 0.2 or sb[3] - sb[1] > height * 1.3:
            continue
        stop = later[1]["start_row_offset_idx"] if len(later) > 1 else data["num_rows"]

        def children(start, end):
            rows = []
            for r in range(start, end):
                labels = [
                    c
                    for c in cells
                    if c["start_row_offset_idx"] == r
                    and c["start_col_offset_idx"] == 0
                    and c["col_span"] == 1
                    and c["row_span"] == 1
                    and c.get("bbox")
                    and c["text"].strip()
                ]
                if len(labels) != 1 or not any(
                    c["start_row_offset_idx"] == r
                    and c["start_col_offset_idx"] > 0
                    and c["text"].strip()
                    for c in cells
                ):
                    return None
                label = labels[0]
                lb = model_box(label["bbox"], page)
                if lb[0] <= xs[1] + height:
                    return None
                rows.append((" ".join(label["text"].split()), lb[0]))
            return rows

        before = children(row + 1, sibling["start_row_offset_idx"])
        after = children(sibling["start_row_offset_idx"] + 1, stop)
        if (
            not before
            or not after
            or len(before) < 2
            or len(before) != len(after)
            or any(
                a[0] != b[0] or abs(a[1] - b[1]) > height * 0.2
                for a, b in zip(before, after)
            )
        ):
            continue
        edits.append((row, cell, groups, lines))
    if not edits:
        return item
    result = deepcopy(item)
    output = []
    byrow = {row: (cell, groups, lines) for row, cell, groups, lines in edits}
    for c in cells:
        oldrow = c["start_row_offset_idx"]
        shift = sum(row < oldrow for row in byrow)
        if any(oldrow < row < c["end_row_offset_idx"] for row in byrow):
            return item
        base = deepcopy(c)
        base["start_row_offset_idx"] += shift
        base["end_row_offset_idx"] += shift
        if oldrow not in byrow:
            output.append(base)
            continue
        original, groups, lines = byrow[oldrow]
        for i in range(2):
            new = deepcopy(base)
            new["start_row_offset_idx"] += i
            new["end_row_offset_idx"] += i
            if c is original:
                part = groups[i]
                new["text"] = lines[i]
                new["bbox"] = local_box(
                    [
                        min(v["x0"] for v in part),
                        min(v["top"] for v in part),
                        max(v["x1"] for v in part),
                        max(v["bottom"] for v in part),
                    ],
                    page,
                )
            output.append(new)
    if Counter(t for c in cells for t in c["text"].split()) != Counter(
        t for c in output for t in c["text"].split()
    ):
        return item
    result["data"].update(table_cells=output, num_rows=data["num_rows"] + len(edits))
    return result
