"""Remove one model-only column when continuous source separators prove the grid."""

from collections import Counter, defaultdict
from copy import deepcopy
from statistics import median
import math
import unicodedata

from pdfplumber.utils import cluster_objects, extract_text
from layout_tables import model_box, local_box, physical_page, visible_box


def canonical(text):
    return "".join(unicodedata.normalize("NFKC", text).split())


def continuous_cuts(page, box):
    left, top, right, bottom = box
    edges = [
        e
        for e in physical_page(page).edges
        if e["orientation"] == "v"
        and left - 4 <= e["x0"] <= right + 4
        and e["bottom"] >= top
        and e["top"] <= bottom
    ]
    cuts = []
    for group in cluster_objects(edges, lambda e: e["x0"], 1.25):
        intervals = []
        for edge in sorted(group, key=lambda e: e["top"]):
            if intervals and edge["top"] <= intervals[-1][1] + 1.5:
                intervals[-1][1] = max(intervals[-1][1], edge["bottom"])
            else:
                intervals.append([edge["top"], edge["bottom"]])
        if any(a <= top + 4 and b >= bottom - 4 for a, b in intervals):
            cuts.append(median(e["x0"] for e in group))
    return cuts


def recover(item, page):
    data = item["data"]
    cols, rows = data["num_cols"], data["num_rows"]
    cells = data["table_cells"]
    if (
        not hasattr(page, "chars")
        or getattr(page, "rotation", 0)
        or not 3 <= cols <= 30
        or not 6 <= rows <= 300
    ):
        return item
    if any(c["row_span"] != 1 or c["col_span"] != 1 for c in cells):
        return item
    box = model_box(item["prov"][0]["bbox"], page)
    view = visible_box(page)
    if not all(math.isfinite(v) for v in box) or not (
        view[0] <= box[0] < box[2] <= view[2] and view[1] <= box[1] < box[3] <= view[3]
    ):
        return item
    left, top, right, bottom = box
    cuts = continuous_cuts(page, box)
    if (
        len(cuts) != cols
        or abs(cuts[0] - left) > 4
        or abs(cuts[-1] - right) > 4
        or any(b - a < 10 for a, b in zip(cuts, cuts[1:]))
    ):
        return item
    mapping = defaultdict(set)
    grouped = defaultdict(list)
    active = [c for c in cells if c["text"].strip()]
    for cell in active:
        if not cell.get("bbox"):
            return item
        b = model_box(cell["bbox"], page)
        destinations = [
            i
            for i, (l, r) in enumerate(zip(cuts, cuts[1:]))
            if l - 1 <= b[0] < b[2] <= r + 1
        ]
        if len(destinations) != 1:
            return item
        col = destinations[0]
        mapping[cell["start_col_offset_idx"]].add(col)
        grouped[(cell["start_row_offset_idx"], col)].append(cell)
    if set(mapping) != set(range(cols)) or any(
        len(values) != 1 for values in mapping.values()
    ):
        return item
    mapped = [next(iter(mapping[i])) for i in range(cols)]
    if mapped != sorted(mapped) or set(mapped) != set(range(cols - 1)):
        return item
    duplicates = [entries for entries in grouped.values() if len(entries) > 1]
    if (
        len(duplicates) != 1
        or len(duplicates[0]) != 2
        or any(
            not c.get("column_header")
            or c["start_row_offset_idx"] != 0
            or any(ch.isdigit() for ch in c["text"])
            for c in duplicates[0]
        )
    ):
        return item
    if any(
        sum(
            c["start_row_offset_idx"] > 0 and mapped[c["start_col_offset_idx"]] == col
            for c in active
        )
        < 3
        for col in range(cols - 1)
    ):
        return item
    chars = [
        c
        for c in page.chars
        if c["text"].strip()
        and left <= (c["x0"] + c["x1"]) / 2 <= right
        and top <= (c["top"] + c["bottom"]) / 2 <= bottom
    ]
    if Counter(canonical("".join(c["text"] for c in chars))) != Counter(
        canonical("".join(c["text"] for c in active))
    ):
        return item
    pair = sorted(duplicates[0], key=lambda c: model_box(c["bbox"], page)[0])
    boxes = [model_box(c["bbox"], page) for c in pair]
    joined = [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    ]
    if abs(sum(boxes[0][1::2]) / 2 - sum(boxes[1][1::2]) / 2) > 2:
        return item
    source = [
        c
        for c in chars
        if joined[0] - 0.5 <= (c["x0"] + c["x1"]) / 2 <= joined[2] + 0.5
        and joined[1] - 0.5 <= (c["top"] + c["bottom"]) / 2 <= joined[3] + 0.5
    ]
    text = extract_text(source, x_tolerance=2, y_tolerance=2) if source else ""
    if "\n" in text or canonical(text) != canonical("".join(c["text"] for c in pair)):
        return item
    result = deepcopy(item)
    output = []
    for entries in grouped.values():
        cell = deepcopy(entries[0])
        col = mapped[cell["start_col_offset_idx"]]
        cell.update(start_col_offset_idx=col, end_col_offset_idx=col + 1)
        if len(entries) > 1:
            cell.update(text=text, bbox=local_box(joined, page))
        output.append(cell)
    result["data"].update(num_cols=cols - 1, table_cells=output)
    return result
