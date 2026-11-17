"""Restore bold section spans only with full-width rule and source-glyph evidence."""

from copy import deepcopy
from statistics import median
from layout_tables import model_box, physical_page
from layout_rows import canon


def restore_section_headers(item, page):
    if not hasattr(page, "chars"):
        return item
    item = deepcopy(item)
    d = item["data"]
    cells = d["table_cells"]
    cols = d["num_cols"]
    bounds = model_box(item["prov"][0]["bbox"], page)
    if cols < 3 or d["num_rows"] < 4:
        return item
    for cell in list(cells):
        row = cell["start_row_offset_idx"]
        if not (
            0 < row < d["num_rows"] - 1
            and cell["start_col_offset_idx"] == 0
            and cell["row_span"] == cell["col_span"] == 1
            and cell.get("bbox")
            and cell["text"].strip()
            and sum(c.isalpha() for c in cell["text"]) >= 3
        ):
            continue
        others = [
            c
            for c in cells
            if c is not cell
            and c["start_row_offset_idx"] <= row < c["end_row_offset_idx"]
            and c["text"].strip()
        ]
        if any(any(ch.isdigit() for ch in c["text"]) for c in others):
            continue
        end = min((c["start_col_offset_idx"] for c in others), default=cols)
        if end < 3:
            continue
        members = [
            c
            for c in cells
            if c["start_row_offset_idx"] <= row < c["end_row_offset_idx"]
            and c["start_col_offset_idx"] < end
        ]
        if any(
            c["row_span"] != 1
            or c["col_span"] != 1
            or (c is not cell and c["text"].strip())
            for c in members
        ):
            continue
        numeric = [
            c
            for c in cells
            if c["start_row_offset_idx"] == row + 1
            and c["start_col_offset_idx"] > 0
            and any(ch.isdigit() for ch in c["text"])
        ]
        if len(numeric) < 2:
            continue
        box = model_box(cell["bbox"], page)
        box[2] = min(
            [model_box(c["bbox"], page)[0] - 1 for c in others if c.get("bbox")]
            + [bounds[2]]
        )
        chars = [
            c
            for c in page.chars
            if box[0] - 1 <= (c["x0"] + c["x1"]) / 2 <= box[2] + 1
            and box[1] - 1 <= (c["top"] + c["bottom"]) / 2 <= box[3] + 1
        ]
        letters = [c for c in chars if any(ch.isalpha() for ch in c["text"])]
        if (
            not letters
            or sum("bold" in c["fontname"].lower() for c in letters)
            < len(letters) * 0.9
        ):
            continue
        from pdfplumber.utils import extract_text

        if canon(extract_text(chars, x_tolerance=2, y_tolerance=3)) != canon(
            cell["text"]
        ):
            continue
        edges = physical_page(page).edges
        top = min(c["top"] for c in chars)
        bottom = max(c["bottom"] for c in chars)
        height = median(c["height"] for c in chars)
        if not any(
            e["orientation"] == "h"
            and bounds[0] - 3 <= e["x0"] <= bounds[0] + 3
            and e["x1"] >= bounds[2] - 3
            and top - height * 0.85 <= e["top"] <= top + 1
            for e in edges
        ):
            continue
        if any(
            e["orientation"] == "v"
            and bounds[0] + 3 < e["x0"] < bounds[2] - 3
            and e["top"] <= top
            and e["bottom"] >= bottom
            for e in edges
        ):
            continue
        cells[:] = [c for c in cells if c is cell or c not in members]
        cell.update(col_span=end, end_col_offset_idx=end)
    return item
