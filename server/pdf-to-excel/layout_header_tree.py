"""Recover a complete multi-level header from native text and physical rules.
Requires exact source character coverage, nested/disjoint underline spans,
repeated body-column anchors, and source-backed leaf labels in the same column.
"""

from collections import Counter
from copy import deepcopy
from statistics import median
import math, re
from pdfplumber.utils import cluster_objects, extract_text
from layout_tables import model_box, local_box, physical_page, visible_box
from source_phrases import canonical


def source_header_edges(page):
    """Treat the two edges of a thin filled underline as one source rule."""
    physical = physical_page(page)
    edges = [dict(edge) for edge in physical.edges]
    for rect in getattr(physical, "rects", []):
        if not rect.get("fill") or rect.get("stroke"):
            continue
        x0, x1, top, bottom = [
            rect.get(k, math.nan) for k in ("x0", "x1", "top", "bottom")
        ]
        if not all(
            isinstance(v, (int, float)) and math.isfinite(v)
            for v in (x0, x1, top, bottom)
        ) or not (0 < bottom - top <= 1.5 and x1 - x0 >= 10):
            continue
        for edge in edges:
            if (
                edge["orientation"] == "h"
                and abs(edge["x0"] - x0) <= 0.25
                and abs(edge["x1"] - x1) <= 0.25
                and top - 0.01 <= edge["top"] <= bottom + 0.01
            ):
                edge["top"] = edge["bottom"] = (top + bottom) / 2
    return edges


def recover(item, page):
    # Keep the already verified path before trying whole-word recovery.
    original = _recover(item, page, False)
    return original if original is not item else _recover(item, page, True)


def _recover(item, page, complete_words):
    data = item["data"]
    cells = data["table_cells"]
    cols = data["num_cols"]
    if (
        not hasattr(page, "chars")
        or (complete_words and not hasattr(page, "extract_words"))
        or getattr(page, "rotation", 0)
        or not 3 <= cols <= 30
    ):
        return item
    header_end = max(
        (c["end_row_offset_idx"] for c in cells if c.get("column_header")), default=0
    )
    if not 2 <= header_end <= 4 or data["num_rows"] < header_end + 3:
        return item
    headers = [c for c in cells if c["start_row_offset_idx"] < header_end]
    body = [c for c in cells if c["start_row_offset_idx"] >= header_end]
    if any(c["end_row_offset_idx"] > header_end for c in headers):
        return item
    if not complete_words and any(
        c["text"].strip() and not c.get("column_header") for c in headers
    ):
        return item
    bounds = model_box(item["prov"][0]["bbox"], page)
    view = visible_box(page)
    if not all(math.isfinite(v) for v in bounds):
        return item
    anchors = []
    for col in range(cols):
        boxes = [
            model_box(c["bbox"], page)
            for c in body
            if c.get("bbox")
            and c["text"].strip()
            and c["col_span"] == 1
            and c["start_col_offset_idx"] == col
        ]
        if len(boxes) < 3:
            return item
        anchors.append(median((b[0] + b[2]) / 2 for b in boxes))
    if any(b - a < 5 for a, b in zip(anchors, anchors[1:])):
        return item
    hb = [
        model_box(c["bbox"], page)
        for c in headers
        if c.get("bbox") and c["text"].strip()
    ]
    bb = [
        model_box(c["bbox"], page) for c in body if c.get("bbox") and c["text"].strip()
    ]
    if not hb or not bb:
        return item
    top = min(b[1] for b in hb)
    bottom = max(b[3] for b in hb)
    bodytop = min(b[1] for b in bb)
    if bottom > bodytop + 1:
        return item
    rules = []
    edges = [
        e
        for e in source_header_edges(page)
        if e["orientation"] == "h"
        and bounds[1] - 3 <= e["top"] <= bodytop
        and e["x1"] > bounds[0]
        and e["x0"] < bounds[2]
    ]
    for group in cluster_objects(edges, lambda e: e["top"], 0.5):
        merged = []
        for e in sorted(group, key=lambda e: e["x0"]):
            if merged and e["x0"] <= merged[-1]["x1"] + 1:
                merged[-1]["x1"] = max(merged[-1]["x1"], e["x1"])
            else:
                merged.append(dict(e))
        for e in merged:
            covered = [c for c, x in enumerate(anchors) if e["x0"] <= x <= e["x1"]]
            if len(covered) >= 2 and covered == list(
                range(min(covered), max(covered) + 1)
            ):
                rules.append(dict(e, columns=covered))
    full = [r for r in rules if len(r["columns"]) == cols]
    above = [r["top"] for r in full if r["top"] <= top + 1]
    below = [r["top"] for r in full if bottom - 1 <= r["top"] <= bodytop]
    if not above or not below:
        return item
    start = max(above)
    end = min(below)
    internal = [
        r
        for r in rules
        if len(r["columns"]) < cols and start + 0.5 < r["top"] < end - 0.5
    ]
    levels = cluster_objects(internal, lambda r: r["top"], 0.5)
    source_header_end = len(levels) + 1
    if not 2 <= source_header_end <= header_end:
        return item
    reducing = source_header_end < header_end
    cuts = [start] + [median(r["top"] for r in group) for group in levels] + [end]
    if any(b - a < 5 for a, b in zip(cuts, cuts[1:])):
        return item
    chars = [
        c
        for c in page.chars
        if view[0] <= c["x0"] <= c["x1"] <= view[2]
        and view[1] <= c["top"] <= c["bottom"] <= view[3]
        and bounds[0] - 1 <= (c["x0"] + c["x1"]) / 2 <= bounds[2] + 1
        and start < (c["top"] + c["bottom"]) / 2 < end
    ]
    if not chars or len(chars) > 3000 or any(not c.get("upright") for c in chars):
        return item
    old = Counter(canonical("".join(c["text"] for c in headers)))
    if old != Counter(canonical("".join(c["text"] for c in chars))):
        return item
    used = set()
    new = []
    occupied = set()

    def add(text, part, row, col, rs, cs):
        region = {(r, c) for r in range(row, row + rs) for c in range(col, col + cs)}
        if region & occupied:
            return False
        occupied.update(region)
        used.update(id(c) for c in part)
        box = [
            min(c["x0"] for c in part),
            min(c["top"] for c in part),
            max(c["x1"] for c in part),
            max(c["bottom"] for c in part),
        ]
        new.append(
            dict(
                start_row_offset_idx=row,
                end_row_offset_idx=row + rs,
                start_col_offset_idx=col,
                end_col_offset_idx=col + cs,
                row_span=rs,
                col_span=cs,
                text=text,
                bbox=local_box(box, page),
                column_header=True,
                row_header=False,
                row_section=False,
            )
        )
        return True

    for row, group in enumerate(levels):
        for rule in group:
            part = [
                c
                for c in chars
                if cuts[row] < (c["top"] + c["bottom"]) / 2 < cuts[row + 1]
                and rule["x0"] <= (c["x0"] + c["x1"]) / 2 <= rule["x1"]
            ]
            if not part:
                return item
            for line in cluster_objects(
                [c for c in part if c["text"].strip()],
                lambda c: (c["top"] + c["bottom"]) / 2,
                2,
            ):
                ordered = sorted(line, key=lambda c: c["x0"])
                height = median(c["bottom"] - c["top"] for c in line)
                if any(
                    b["x0"] - a["x1"] > height * 0.8
                    for a, b in zip(ordered, ordered[1:])
                ):
                    return item
            text = extract_text(part, x_tolerance=2, y_tolerance=3)
            if not text.strip() or not (
                any(c.isalpha() for c in text)
                or (complete_words and re.fullmatch(r"[0-9]{4}", text.strip()))
            ):
                return item
            if reducing and not any(
                canonical(text) in canonical(cell["text"]) for cell in headers
            ):
                return item
            current = set(rule["columns"])
            for parent in new:
                ancestor = set(
                    range(parent["start_col_offset_idx"], parent["end_col_offset_idx"])
                )
                if (
                    parent["start_row_offset_idx"] < row
                    and current & ancestor
                    and not current <= ancestor
                ):
                    return item
            if not add(text, part, row, rule["columns"][0], 1, len(rule["columns"])):
                return item
    borders = (
        [bounds[0]] + [(a + b) / 2 for a, b in zip(anchors, anchors[1:])] + [bounds[2]]
    )
    admitted = {id(c) for c in chars if c["text"].strip()}
    words = (
        [
            w
            for w in page.extract_words(x_tolerance=2, y_tolerance=3, return_chars=True)
            if w["chars"]
            and all(id(c) in admitted for c in w["chars"] if c["text"].strip())
        ]
        if complete_words
        else []
    )
    word_owners = {}
    if complete_words:
        for word in words:
            x = (word["x0"] + word["x1"]) / 2
            y = (word["top"] + word["bottom"]) / 2
            candidates = set()
            for cell in headers:
                if cell["col_span"] != 1 or not cell.get("bbox"):
                    continue
                if canonical(word["text"]) not in {
                    canonical(token) for token in cell["text"].split()
                }:
                    continue
                b = model_box(cell["bbox"], page)
                if b[0] - 1 <= x <= b[2] + 1 and b[1] - 1 <= y <= b[3] + 1:
                    candidates.add(cell["start_col_offset_idx"])
            if len(candidates) == 1:
                word_owners[id(word)] = candidates.pop()
    for col, (left, right) in enumerate(zip(borders, borders[1:])):
        first = max(
            (
                c["end_row_offset_idx"]
                for c in new
                if c["start_col_offset_idx"] <= col < c["end_col_offset_idx"]
            ),
            default=0,
        )
        if complete_words:
            # Assign complete source words, never a clipped fragment of a label.
            leaf_words = [
                w
                for w in words
                if (
                    word_owners[id(w)] == col
                    if id(w) in word_owners
                    else left <= (w["x0"] + w["x1"]) / 2 < right
                )
                and all(id(c) not in used for c in w["chars"] if c["text"].strip())
            ]
            part = [c for w in leaf_words for c in w["chars"] if id(c) in admitted]
            if not part or any(
                (c["top"] + c["bottom"]) / 2 < cuts[first] for c in part
            ):
                return item
            lines = cluster_objects(
                leaf_words, lambda w: (w["top"] + w["bottom"]) / 2, 2
            )
            text = "\n".join(
                " ".join(w["text"] for w in sorted(line, key=lambda w: w["x0"]))
                for line in lines
            )
        else:
            leaf_boxes = [
                model_box(c["bbox"], page)
                for c in headers
                if c.get("bbox")
                and c["start_col_offset_idx"] == col
                and c["col_span"] == 1
                and c["text"].strip()
            ]
            part = [
                c
                for c in chars
                if id(c) not in used
                and any(
                    b[0] - 1 <= (c["x0"] + c["x1"]) / 2 <= b[2] + 1
                    and b[1] - 1 <= (c["top"] + c["bottom"]) / 2 <= b[3] + 1
                    for b in leaf_boxes
                )
            ]
            if not part or any(
                (c["top"] + c["bottom"]) / 2 < cuts[first] for c in part
            ):
                return item
            text = extract_text(part, x_tolerance=2, y_tolerance=3)
        prior = " ".join(
            c["text"]
            for c in headers
            if c["start_col_offset_idx"] <= col < c["end_col_offset_idx"]
            and (
                c["col_span"] == 1 or c["start_row_offset_idx"] >= source_header_end - 1
            )
        )
        # Model fragments may place the middle line after the first/last lines.
        # Only complete source words present in this same column may be reordered.
        same_words = complete_words and not (
            Counter(canonical(w) for w in text.split())
            - Counter(canonical(w) for w in prior.split())
        )
        if not canonical(text) or (
            canonical(text) not in canonical(prior) and not same_words
        ):
            return item
        ink = [c for c in part if c["text"].strip()]
        lo = min(c["x0"] for c in ink)
        hi = max(c["x1"] for c in ink)
        last = max(c["bottom"] for c in ink)
        if any(
            cuts[first] + 0.5 < e["top"] < last
            and min(hi, e["x1"]) - max(lo, e["x0"]) >= (hi - lo) * 0.8
            for e in edges
        ):
            return item
        if not add(text, part, first, col, source_header_end - first, 1):
            return item
    if len(occupied) != cols * source_header_end or any(
        c["text"].strip() and id(c) not in used for c in chars
    ):
        return item
    if Counter(canonical("".join(c["text"] for c in new))) != old:
        return item
    signature = lambda entries: sorted(
        (
            c["start_row_offset_idx"],
            c["start_col_offset_idx"],
            c["row_span"],
            c["col_span"],
            canonical(c["text"]),
        )
        for c in entries
        if c["text"].strip()
    )
    if signature(new) == signature(headers):
        return item
    result = deepcopy(item)
    shifted = deepcopy(body)
    for cell in shifted:
        cell["start_row_offset_idx"] += source_header_end - header_end
        cell["end_row_offset_idx"] += source_header_end - header_end
    result["data"]["table_cells"] = shifted + new
    result["data"]["num_rows"] += source_header_end - header_end
    return result
