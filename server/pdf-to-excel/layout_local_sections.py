"""Split a locally merged native section label and record using same-table evidence.

This does not rebuild the body or infer values. Two independently separated
section/record pairs must corroborate typography, indentation and vertical
rhythm. Only an exact two-line first-column source sequence is eligible.
"""

import math
import re
from collections import Counter, defaultdict
from copy import deepcopy
from numbers import Real
from statistics import median

from layout_tables import local_box, model_box, physical_page, visible_box
from pdfplumber.utils import cluster_objects, extract_text


def _compact(text):
    return "".join(text.split())


def _finite(values):
    return all(isinstance(v, Real) and math.isfinite(v) for v in values)


def _bounds(chars):
    return [
        min(c["x0"] for c in chars),
        min(c["top"] for c in chars),
        max(c["x1"] for c in chars),
        max(c["bottom"] for c in chars),
    ]


def _number(text):
    return bool(
        re.fullmatch(
            r"(?:[†‡—–-]|[$€£¥]?[+−-]?(?:[0-9]+(?:[.,][0-9]+)?|[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?)(?:%|[*†‡])?)",
            _compact(text),
        )
    )


def recover(item, page):
    data = item["data"]
    cols, count = data["num_cols"], data["num_rows"]
    if (
        not isinstance(cols, int)
        or not isinstance(count, int)
        or getattr(page, "rotation", 0)
        or not 3 <= cols <= 30
        or not 8 <= count <= 300
    ):
        return item
    cells = data["table_cells"]
    if not isinstance(cells, list) or len(cells) > count * cols:
        return item
    rows = defaultdict(list)
    occupied = set()
    for c in cells:
        keys = (
            "start_row_offset_idx",
            "end_row_offset_idx",
            "start_col_offset_idx",
            "end_col_offset_idx",
            "row_span",
            "col_span",
        )
        if (
            not isinstance(c, dict)
            or not isinstance(c.get("text"), str)
            or any(
                not isinstance(c.get(k), int) or isinstance(c.get(k), bool)
                for k in keys
            )
        ):
            return item
        r, end_r, col, end_col, rs, cs = (c[k] for k in keys)
        if not (
            0 <= r < end_r <= count
            and 0 <= col < end_col <= cols
            and rs == end_r - r
            and cs == end_col - col
        ):
            return item
        region = {(y, x) for y in range(r, end_r) for x in range(col, end_col)}
        if occupied & region:
            return item
        occupied.update(region)
        rows[r].append(c)
    view = visible_box(page)
    box = model_box(item["prov"][0]["bbox"], page)
    if not _finite(view + box) or not (
        view[0] <= box[0] < box[2] <= view[2] and view[1] <= box[1] < box[3] <= view[3]
    ):
        return item
    chars = [c for c in page.chars if c.get("text", "").strip()]
    if len(chars) > 50000 or any(
        not _finite([c.get(k) for k in ("x0", "x1", "top", "bottom", "size")])
        for c in chars
    ):
        return item
    bands = defaultdict(list)
    for c in chars:
        bands[math.floor((c["top"] + c["bottom"]) / 32)].append(c)
    cache = {}

    def lines(cell):
        key = id(cell)
        if key in cache:
            return cache[key]
        cache[key] = None
        if not cell.get("bbox") or not cell["text"].strip():
            return None
        b = model_box(cell["bbox"], page)
        if (
            not _finite(b)
            or not (
                view[0] <= b[0] < b[2] <= view[2] and view[1] <= b[1] < b[3] <= view[3]
            )
            or b[3] - b[1] > 60
        ):
            return None
        selected = [
            c
            for band in range(
                math.floor((b[1] - 0.5) / 16), math.floor((b[3] + 0.5) / 16) + 1
            )
            for c in bands[band]
            if b[0] - 0.2 <= (c["x0"] + c["x1"]) / 2 <= b[2] + 0.2
            and b[1] - 0.5 <= (c["top"] + c["bottom"]) / 2 <= b[3] + 0.5
        ]
        if not selected or any(
            not c.get("upright")
            or not (4 <= c["size"] <= 20)
            or not (
                view[0] <= c["x0"] < c["x1"] <= view[2]
                and view[1] <= c["top"] < c["bottom"] <= view[3]
            )
            or not c.get("fontname")
            or not c.get("matrix")
            or len(c["matrix"]) != 6
            or not _finite(c["matrix"])
            or c["matrix"][0] <= 0
            or c["matrix"][3] <= 0
            or abs(c["matrix"][1]) > 0.001
            or abs(c["matrix"][2]) > 0.001
            for c in selected
        ):
            return None
        height = median(c["size"] for c in selected)
        groups = cluster_objects(
            selected, lambda c: (c["top"] + c["bottom"]) / 2, min(1.5, height * 0.15)
        )
        result = []
        for group in groups:
            if (
                max(c["top"] for c in group) - min(c["top"] for c in group) > 0.7
                or max(c["size"] for c in group) - min(c["size"] for c in group) > 0.2
            ):
                return None
            result.append(
                {
                    "chars": group,
                    "text": extract_text(group, x_tolerance=1.5, y_tolerance=2),
                    "box": _bounds(group),
                    "y": median((c["top"] + c["bottom"]) / 2 for c in group),
                    "size": median(c["size"] for c in group),
                    "fonts": frozenset(c["fontname"] for c in group),
                }
            )
        if _compact(cell["text"]) != "".join(_compact(line["text"]) for line in result):
            return None
        cache[key] = result
        return result

    def row_data(r):
        row = rows.get(r, [])
        if len(row) != cols or any(
            c["row_span"] != 1
            or c["col_span"] != 1
            or c.get("column_header")
            or not c["text"].strip()
            for c in row
        ):
            return None
        indexed = {c["start_col_offset_idx"]: c for c in row}
        if set(indexed) != set(range(cols)) or any(
            not _number(indexed[i]["text"]) for i in range(1, cols)
        ):
            return None
        groups = [lines(indexed[i]) for i in range(cols)]
        if any(not group or len(group) != 1 for group in groups):
            return None
        flat = [group[0] for group in groups]
        if max(line["y"] for line in flat) - min(line["y"] for line in flat) > 1:
            return None
        return flat

    def only_line(line):
        # Model emptiness is not evidence: inspect every native glyph touching
        # the full-width source band, including shifted/superscript values.
        touching = [
            c
            for c in chars
            if c["x1"] > box[0] + 0.05
            and c["x0"] < box[2] - 0.05
            and c["bottom"] > line["box"][1] + 0.05
            and c["top"] < line["box"][3] - 0.05
        ]
        return {id(c) for c in touching} == {id(c) for c in line["chars"]}

    references = []
    for r, row in rows.items():
        nonempty = [c for c in row if c["text"].strip()]
        if len(nonempty) != 1:
            continue
        head = nonempty[0]
        if (
            head["start_col_offset_idx"] != 0
            or head["row_span"] != 1
            or head["col_span"] != 1
            or head.get("column_header")
        ):
            continue
        heading, before, after = lines(head), row_data(r - 1), row_data(r + 1)
        if not heading or len(heading) != 1 or not before or not after:
            continue
        h = heading[0]
        if not only_line(h):
            continue
        indent, pre, post = (
            after[0]["box"][0] - h["box"][0],
            h["y"] - before[0]["y"],
            after[0]["y"] - h["y"],
        )
        if (
            h["size"] * 0.3 <= indent <= h["size"] * 1.2
            and h["size"] <= post <= h["size"] * 1.6
            and post * 1.4 <= pre <= post * 2.4
        ):
            references.append((h, indent, pre, post))
    if len(references) < 2:
        return item
    verticals = [e for e in physical_page(page).edges if e.get("orientation") == "v"]
    if any(
        not _finite([e.get(k) for k in ("x0", "x1", "top", "bottom")])
        for e in verticals
    ):
        return item
    candidates = []
    for r, row in rows.items():
        left = next((c for c in row if c["start_col_offset_idx"] == 0), None)
        if (
            left is None
            or left.get("column_header")
            or left["row_span"] != 1
            or left["col_span"] != 1
        ):
            continue
        split = lines(left)
        if not split or len(split) != 2:
            continue
        upper, lower = split
        neighbors = [c for c in row if c is not left]
        if (
            len(neighbors) != cols - 1
            or {c["start_col_offset_idx"] for c in neighbors} != set(range(1, cols))
            or any(
                c["row_span"] != 1 or c["col_span"] != 1 or not _number(c["text"])
                for c in neighbors
            )
        ):
            continue
        numeric = [lines(c) for c in neighbors]
        before, after = row_data(r - 1), row_data(r + 1)
        if (
            not before
            or not after
            or any(
                not group or len(group) != 1 or abs(group[0]["y"] - lower["y"]) > 1
                for group in numeric
            )
        ):
            continue
        matching = [
            ref
            for ref in references
            if ref[0]["fonts"] == upper["fonts"] == lower["fonts"]
            and abs(ref[0]["size"] - upper["size"]) <= 0.2
            and abs(upper["size"] - lower["size"]) <= 0.2
            and abs(ref[0]["box"][0] - upper["box"][0]) <= 1
            and abs(ref[1] - (lower["box"][0] - upper["box"][0])) <= upper["size"] * 0.3
            and abs(ref[2] - (upper["y"] - before[0]["y"])) <= 1.5
            and abs(ref[3] - (lower["y"] - upper["y"])) <= 1
            and abs(ref[3] - (after[0]["y"] - lower["y"])) <= 1
        ]
        if len(matching) < 2:
            continue
        # Reject a closed grid's wrapped cell and any other content on the
        # proposed section line, including values omitted by the model.
        if any(
            box[0] - 0.5 <= (e["x0"] + e["x1"]) / 2 <= box[2] + 0.5
            and e["top"] <= upper["box"][1] + 1
            and e["bottom"] >= lower["box"][3] - 1
            for e in verticals
        ):
            continue
        if not only_line(upper):
            continue
        if any(
            c["row_span"] > 1
            and c["start_row_offset_idx"] <= r < c["end_row_offset_idx"]
            for c in cells
        ):
            continue
        candidates.append((r, left, upper, lower))
    if not candidates or len(candidates) > 8:
        return item
    result = deepcopy(item)
    updated = deepcopy(cells)
    for r, left, upper, lower in sorted(candidates, reverse=True, key=lambda c: c[0]):
        for c in updated:
            if c["start_row_offset_idx"] > r or (
                c["start_row_offset_idx"] == r and c["start_col_offset_idx"] != 0
            ):
                c["start_row_offset_idx"] += 1
                c["end_row_offset_idx"] += 1
        target = next(
            c
            for c in updated
            if c["start_row_offset_idx"] == r and c["start_col_offset_idx"] == 0
        )
        target.update(text=upper["text"], bbox=local_box(upper["box"], page))
        child = deepcopy(left)
        child.update(
            text=lower["text"],
            bbox=local_box(lower["box"], page),
            start_row_offset_idx=r + 1,
            end_row_offset_idx=r + 2,
        )
        updated.append(child)
    if Counter(_compact("".join(c["text"] for c in cells))) != Counter(
        _compact("".join(c["text"] for c in updated))
    ):
        return item
    result["data"].update(table_cells=updated, num_rows=count + len(candidates))
    return result
