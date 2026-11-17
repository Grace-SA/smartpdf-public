"""Recover collapsed native-text rows using independently aligned source lines.

This module never receives reference annotations. Two numeric columns must agree
on the source baselines, every predicted value must survive in its own column,
and neighbouring row pitch must support the split. Ambiguous rows stay intact.
"""

import collections
import copy
import math
import re
import statistics
import unicodedata
from pdfplumber.utils import extract_text, cluster_objects
from layout_tables import model_box, local_box, visible_box, physical_page

TRANS = str.maketrans(
    {"–": "-", "—": "-", "−": "-", "‘": "'", "’": "'", "“": '"', "”": '"', "•": "·"}
)


def canon(v):
    return "".join(unicodedata.normalize("NFKC", v).translate(TRANS).casefold().split())


def numeric(v):
    return bool(re.fullmatch(r"[\d.,%()+−–—\- *†‡]+", v.strip())) and any(
        c.isdigit() for c in v
    )


def repair_merged_rows(item, page):
    item = copy.deepcopy(item)
    d = item["data"]
    cells = d["table_cells"]
    cols = d["num_cols"]
    rows = d["num_rows"]
    if cols < 3 or rows < 5 or not hasattr(page, "chars"):
        return item
    if any(
        c["start_row_offset_idx"] < 0
        or c["end_row_offset_idx"] > rows
        or c["end_row_offset_idx"] - c["start_row_offset_idx"] != c["row_span"]
        or c["start_col_offset_idx"] < 0
        or c["start_col_offset_idx"] + c["col_span"] > cols
        for c in cells
    ):
        return item
    box = model_box(item["prov"][0]["bbox"], page)
    view = visible_box(page)
    if not all(math.isfinite(v) for v in box) or box[2] <= box[0] or box[3] <= box[1]:
        return item
    byrow = collections.defaultdict(list)
    bycol = collections.defaultdict(list)
    for c in cells:
        byrow[c["start_row_offset_idx"]].append(c)
        if (
            c.get("bbox")
            and c["col_span"] == 1
            and c["text"].strip()
            and not c.get("column_header")
        ):
            bycol[c["start_col_offset_idx"]].append(model_box(c["bbox"], page))
    if any(not bycol[i] for i in range(cols)):
        return item
    # Independent body extents keep clipped model text boxes from truncating names.
    extent = [
        (min(b[0] for b in bycol[i]), max(b[2] for b in bycol[i])) for i in range(cols)
    ]
    edges = (
        [box[0]]
        + [(extent[i - 1][1] + extent[i][0]) / 2 for i in range(1, cols)]
        + [box[2]]
    )
    if any(b <= a for a, b in zip(edges, edges[1:])):
        return item
    centers = []
    for row, group in sorted(byrow.items()):
        nums = [
            c
            for c in group
            if c.get("bbox")
            and c["row_span"] == 1
            and c["col_span"] == 1
            and numeric(c["text"])
            and len(c["text"].split()) == 1
        ]
        if len(nums) >= 2:
            centers.append(
                statistics.median(
                    (model_box(c["bbox"], page)[1] + model_box(c["bbox"], page)[3]) / 2
                    for c in nums
                )
            )
    if len(centers) < 4:
        return item
    spacings = [b - a for a, b in zip(centers, centers[1:]) if b > a]
    if not spacings:
        return item
    pitch = statistics.median(spacings)
    chars = [
        c
        for c in page.chars
        if view[0] <= (c["x0"] + c["x1"]) / 2 <= view[2]
        and view[1] <= (c["top"] + c["bottom"]) / 2 <= view[3]
    ]
    repaired = {}
    rules = getattr(physical_page(page), "edges", [])
    for row, group in sorted(byrow.items()):
        if any(
            c.get("column_header") or c["row_span"] != 1 or c["col_span"] != 1
            for c in group
        ):
            continue
        if any(
            c["start_row_offset_idx"] < row < c["end_row_offset_idx"] for c in cells
        ):
            continue
        if sum(numeric(c["text"]) and len(c["text"].split()) > 1 for c in group) < 2:
            continue
        bounds = [
            model_box(c["bbox"], page)
            for c in group
            if c.get("bbox") and c["text"].strip()
        ]
        if not bounds:
            continue
        top, bottom = min(b[1] for b in bounds), max(b[3] for b in bounds)
        previous = [
            model_box(c["bbox"], page)[3]
            for c in byrow.get(row - 1, [])
            if c.get("bbox") and c["text"].strip()
        ]
        following = [
            model_box(c["bbox"], page)[1]
            for c in byrow.get(row + 1, [])
            if c.get("bbox") and c["text"].strip()
        ]
        if previous:
            top = min(top, statistics.median(previous) + 1)
        if following:
            bottom = max(bottom, statistics.median(following) - 1)
        parsed = {}
        all_lines = {}
        valid = True
        for c in group:
            col = c["start_col_offset_idx"]
            target = canon(c["text"])
            if not target:
                continue
            selected = [
                x
                for x in chars
                if edges[col] <= (x["x0"] + x["x1"]) / 2 < edges[col + 1]
                and top - 1 <= (x["top"] + x["bottom"]) / 2 <= bottom + 1
            ]
            lines = []
            for line in cluster_objects(
                selected, lambda x: (x["top"] + x["bottom"]) / 2, 2.5
            ):
                txt = extract_text(line, x_tolerance=2, y_tolerance=3)
                if txt.strip():
                    lines.append(
                        (
                            txt,
                            statistics.median(
                                (x["top"] + x["bottom"]) / 2 for x in line
                            ),
                            [
                                min(x["x0"] for x in line),
                                min(x["top"] for x in line),
                                max(x["x1"] for x in line),
                                max(x["bottom"] for x in line),
                            ],
                        )
                    )
            if len(lines) > 8:
                valid = False
                break
            matches = [
                lines[a:b]
                for a in range(len(lines))
                for b in range(a + 1, len(lines) + 1)
                if canon("".join(v[0] for v in lines[a:b])) == target
            ]
            if len(matches) != 1:
                valid = False
                break
            parsed[col] = matches[0]
            all_lines[col] = lines
        if not valid or not parsed:
            continue
        counts = collections.Counter(
            len(v)
            for v in parsed.values()
            if len(v) > 1 and all(numeric(line[0]) for line in v)
        )
        if not counts:
            continue
        count, evidence = counts.most_common(1)[0]
        if evidence < 2:
            continue
        for col, v in list(parsed.items()):
            if (
                len(v) < count
                and len(all_lines[col]) == count
                and all(numeric(line[0]) for line in all_lines[col])
            ):
                parsed[col] = all_lines[col]
        if any(len(v) != count for v in parsed.values()):
            continue
        if not 2 <= count <= 4:
            continue
        if sum(all(numeric(line[0]) for line in v) for v in parsed.values()) < 2:
            continue
        ys = [statistics.median(v[i][1] for v in parsed.values()) for i in range(count)]
        if any(
            abs(v[i][1] - ys[i]) > 2.5 for v in parsed.values() for i in range(count)
        ):
            continue
        if any(not 0.75 * pitch <= b - a <= 1.35 * pitch for a, b in zip(ys, ys[1:])):
            continue
        # Explicit cell borders override a row-pitch inference. A box containing
        # several numeric lines can intentionally be a single multiline cell.
        horizontal = [
            e
            for e in rules
            if e.get("orientation") == "h"
            and min(box[2], e["x1"]) - max(box[0], e["x0"]) >= 0.8 * (box[2] - box[0])
        ]
        above = any(ys[0] - pitch <= e["top"] < ys[0] for e in horizontal)
        below = any(ys[-1] < e["top"] <= ys[-1] + pitch for e in horizontal)
        vertical = [
            e
            for e in rules
            if e.get("orientation") == "v"
            and e["top"] <= ys[0]
            and e["bottom"] >= ys[-1]
        ]
        boxed = above and below and len(vertical) >= 2
        if boxed and any(
            not any(a < e["top"] < b for e in horizontal) for a, b in zip(ys, ys[1:])
        ):
            continue
        repaired[row] = (count, parsed)
    if not repaired:
        return item
    shift = [0] * (rows + 1)
    for row in range(rows):
        shift[row + 1] = shift[row] + (repaired[row][0] - 1 if row in repaired else 0)
    new = []
    for c in cells:
        row = c["start_row_offset_idx"]
        col = c["start_col_offset_idx"]
        start = row + shift[row]
        if row in repaired:
            count, parsed = repaired[row]
            for i in range(count):
                n = dict(
                    c,
                    start_row_offset_idx=start + i,
                    end_row_offset_idx=start + i + 1,
                    row_span=1,
                )
                if col in parsed:
                    n["text"] = parsed[col][i][0]
                    n["bbox"] = local_box(parsed[col][i][2], page)
                new.append(n)
        else:
            end = c["end_row_offset_idx"] + shift[c["end_row_offset_idx"]]
            new.append(
                dict(
                    c,
                    start_row_offset_idx=start,
                    end_row_offset_idx=end,
                    row_span=end - start,
                )
            )
    d["table_cells"] = new
    d["num_rows"] += shift[-1]
    return item
