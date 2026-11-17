"""Separate grouped headings from dates using source glyphs and underline spans.

At least three body anchors per column, exact source content, an independent
physical underline, and a vacant destination row are required.
"""

from copy import deepcopy
from statistics import median
from pdfplumber.utils import cluster_objects, extract_text
from layout_tables import model_box, local_box, physical_page, visible_box
from layout_rows import canon, numeric


def restore_underlined_headers(item, page):
    item = deepcopy(item)
    data = item["data"]
    cells = data["table_cells"]
    cols = data["num_cols"]
    if cols < 2 or data["num_rows"] < 4 or not hasattr(page, "chars"):
        return item
    view = visible_box(page)
    anchors = {}
    for col in range(cols):
        boxes = [
            model_box(c["bbox"], page)
            for c in cells
            if c.get("bbox")
            and c["text"].strip()
            and c["start_col_offset_idx"] == col
            and c["col_span"] == 1
            and not c.get("column_header")
        ]
        if len(boxes) < 3:
            return item
        anchors[col] = median((b[0] + b[2]) / 2 for b in boxes)
    if any(anchors[c] >= anchors[c + 1] for c in range(cols - 1)):
        return item
    for cell in list(cells):
        r = cell["start_row_offset_idx"]
        if not (
            1 <= r <= 3
            and cell.get("column_header")
            and cell["row_span"] == 1
            and cell["col_span"] == 1
            and cell.get("bbox")
        ):
            continue
        box = model_box(cell["bbox"], page)
        chars = [
            c
            for c in page.chars
            if view[0] <= c["x0"] <= c["x1"] <= view[2]
            and view[1] <= c["top"] <= c["bottom"] <= view[3]
            and box[0] - 1 <= (c["x0"] + c["x1"]) / 2 <= box[2] + 1
            and box[1] - 1 <= (c["top"] + c["bottom"]) / 2 <= box[3] + 1
        ]
        lines = cluster_objects(chars, lambda c: c["top"], 2)
        if len(lines) != 2:
            continue
        col = cell["start_col_offset_idx"]
        lo = (anchors[col - 1] + anchors[col]) / 2 if col else -float("inf")
        hi = (anchors[col] + anchors[col + 1]) / 2 if col + 1 < cols else float("inf")
        lines[1] = [ch for ch in lines[1] if lo <= (ch["x0"] + ch["x1"]) / 2 < hi]
        if not lines[1]:
            continue
        text = [extract_text(line, x_tolerance=2, y_tolerance=3) for line in lines]
        if (
            not text[0]
            or not any(c.isalpha() for c in text[0])
            or any(c.isdigit() for c in text[0])
            or not numeric(text[1])
            or canon("".join(text)) != canon(cell["text"])
        ):
            continue
        bottom = max(c["bottom"] for c in lines[0])
        top = min(c["top"] for c in lines[1])
        left = min(c["x0"] for c in lines[0])
        right = max(c["x1"] for c in lines[0])
        edges = [
            e
            for e in physical_page(page).edges
            if e.get("orientation") == "h" and bottom - 1 <= e["top"] <= top + 1
        ]
        rules = []
        for group in cluster_objects(edges, lambda e: e["top"], 0.5):
            merged = []
            for edge in sorted(group, key=lambda e: e["x0"]):
                if merged and edge["x0"] <= merged[-1]["x1"] + 1:
                    merged[-1]["x1"] = max(merged[-1]["x1"], edge["x1"])
                else:
                    merged.append(dict(edge))
            rules.extend(e for e in merged if e["x0"] <= left and e["x1"] >= right)
        for edge in sorted(rules, key=lambda e: e["x1"] - e["x0"]):
            covered = [c for c, x in anchors.items() if edge["x0"] <= x <= edge["x1"]]
            if len(covered) < 2 or covered != list(
                range(min(covered), max(covered) + 1)
            ):
                continue
            first, last = min(covered), max(covered) + 1
            if not first <= cell["start_col_offset_idx"] < last:
                continue
            overlaps = [
                c
                for c in cells
                if c["start_row_offset_idx"] <= r - 1 < c["end_row_offset_idx"]
                and c["start_col_offset_idx"] < last
                and c["end_col_offset_idx"] > first
            ]
            if any(
                c["text"].strip()
                or c["row_span"] != 1
                or c["start_col_offset_idx"] < first
                or c["end_col_offset_idx"] > last
                for c in overlaps
            ):
                continue
            cells[:] = [c for c in cells if c not in overlaps]
            new = deepcopy(cell)
            new.update(
                text=text[0],
                start_row_offset_idx=r - 1,
                end_row_offset_idx=r,
                start_col_offset_idx=first,
                end_col_offset_idx=last,
                col_span=last - first,
                bbox=local_box(
                    [left, min(c["top"] for c in lines[0]), right, bottom], page
                ),
            )
            cell["text"] = text[1]
            cell["bbox"] = local_box(
                [
                    min(c["x0"] for c in lines[1]),
                    top,
                    max(c["x1"] for c in lines[1]),
                    max(c["bottom"] for c in lines[1]),
                ],
                page,
            )
            cells.append(new)
            break
    return item
