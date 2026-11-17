"""Repair paragraph spill between rows using verified stub starts and physical columns."""

from collections import Counter, defaultdict
from copy import deepcopy
import math

from pdfplumber.utils import extract_text
from layout_columns import canonical, continuous_cuts
from layout_tables import model_box, local_box, visible_box


def recover(item, page):
    data = item["data"]
    cells = data["table_cells"]
    rows = data["num_rows"]
    cols = data["num_cols"]
    if (
        not hasattr(page, "chars")
        or getattr(page, "rotation", 0)
        or not 5 <= rows <= 40
        or not 2 <= cols <= 5
    ):
        return item
    if any(c["row_span"] != 1 or c["col_span"] != 1 for c in cells):
        return item
    labels = {
        c["start_row_offset_idx"]: c
        for c in cells
        if c["start_col_offset_idx"] == 0 and c["text"].strip()
    }
    if set(labels) != set(range(rows)) or any(
        len(c["text"].split()) > 8 for c in labels.values()
    ):
        return item
    box = model_box(item["prov"][0]["bbox"], page)
    view = visible_box(page)
    if not all(math.isfinite(v) for v in box) or not (
        view[0] <= box[0] < box[2] <= view[2] and view[1] <= box[1] < box[3] <= view[3]
    ):
        return item
    cuts = continuous_cuts(page, box)
    if (
        len(cuts) != cols + 1
        or abs(cuts[0] - box[0]) > 4
        or abs(cuts[-1] - box[2]) > 4
        or any(b - a < 20 for a, b in zip(cuts, cuts[1:]))
    ):
        return item
    chars = [
        c
        for c in page.chars
        if c["text"].strip()
        and box[0] <= (c["x0"] + c["x1"]) / 2 <= box[2]
        and box[1] <= (c["top"] + c["bottom"]) / 2 <= box[3]
    ]
    if not chars or len(chars) > 20000 or any(not c.get("upright") for c in chars):
        return item
    if Counter(canonical("".join(c["text"] for c in chars))) != Counter(
        canonical("".join(c["text"] for c in cells))
    ):
        return item
    starts = []
    for row in range(rows):
        cell = labels[row]
        if not cell.get("bbox"):
            return item
        b = model_box(cell["bbox"], page)
        glyphs = [
            c
            for c in chars
            if b[0] - 0.5 <= (c["x0"] + c["x1"]) / 2 <= b[2] + 0.5
            and b[1] - 0.5 <= (c["top"] + c["bottom"]) / 2 <= b[3] + 0.5
        ]
        if not glyphs or canonical(
            extract_text(glyphs, x_tolerance=2, y_tolerance=2)
        ) != canonical(cell["text"]):
            return item
        starts.append(min(c["top"] for c in glyphs) - 1)
    if any(b - a < 6 for a, b in zip(starts, starts[1:])):
        return item
    starts[0] = box[1]
    starts.append(box[3] + 1)
    grouped = defaultdict(list)
    for char in chars:
        x = (char["x0"] + char["x1"]) / 2
        y = (char["top"] + char["bottom"]) / 2
        col = next(
            (i for i, (l, r) in enumerate(zip(cuts, cuts[1:])) if l <= x < r), None
        )
        row = next(
            (i for i, (t, b) in enumerate(zip(starts, starts[1:])) if t <= y < b), None
        )
        if col is None or row is None:
            return item
        grouped[row, col].append(char)
    before = {
        (c["start_row_offset_idx"], c["start_col_offset_idx"]): c
        for c in cells
        if c["text"].strip()
    }
    if set(grouped) != set(before):
        return item
    output = []
    changed = 0
    aligned = 0
    for (row, col), glyphs in grouped.items():
        cell = before[row, col]
        text = extract_text(glyphs, x_tolerance=2, y_tolerance=2)
        if col == 0 and canonical(text) != canonical(cell["text"]):
            return item
        if row and col:
            # Numeric records and short values require a different row model.
            if len(text.split()) < 4 or not any(ch.isalpha() for ch in text):
                return item
            if abs(min(c["top"] for c in glyphs) - (starts[row] + 1)) > 2:
                return item
            aligned += 1
        same = canonical(text) == canonical(cell["text"])
        if not same:
            changed += 1
        new = deepcopy(cell)
        if not same:
            new.update(
                text=text,
                bbox=local_box(
                    [
                        min(c["x0"] for c in glyphs),
                        min(c["top"] for c in glyphs),
                        max(c["x1"] for c in glyphs),
                        max(c["bottom"] for c in glyphs),
                    ],
                    page,
                ),
            )
        output.append(new)
    if aligned < 4 or not changed:
        return item
    result = deepcopy(item)
    result["data"]["table_cells"] = output
    return result
