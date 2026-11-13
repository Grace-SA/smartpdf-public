"""Complete native row recovery inside a model-located numeric body.
No source references, document IDs, or expected values enter this function.
"""

import copy, math, re
from collections import defaultdict, Counter
from statistics import median
from pdfplumber.utils import cluster_objects, extract_text
from layout_tables import model_box, local_box, physical_page, visible_box


def numeric(value):
    return bool(
        re.fullmatch(
            r"[+−–—-]?(?:\d[\d., ]*|\.\d+)(?:%|\*|†|‡)?|\([\d., ]+\)", value.strip()
        )
    )


def recover(item, page):
    data = item["data"]
    cols = data["num_cols"]
    cells = data["table_cells"]
    if (
        not hasattr(page, "extract_words")
        or not hasattr(page, "chars")
        or getattr(page, "rotation", 0)
        or not 4 <= cols <= 30
        or data["num_rows"] < 10
    ):
        return item
    box = model_box(item["prov"][0]["bbox"], page)
    view = visible_box(page)
    if not all(math.isfinite(v) for v in box) or not (
        view[0] <= box[0] < box[2] <= view[2] and view[1] <= box[1] < box[3] <= view[3]
    ):
        return item
    extents = defaultdict(list)
    for cell in cells:
        if (
            cell.get("bbox")
            and cell["col_span"] == 1
            and cell["text"].strip()
            and not cell.get("column_header")
        ):
            extents[cell["start_col_offset_idx"]].append(model_box(cell["bbox"], page))
    if any(not extents[col] for col in range(cols)):
        return item
    edges = (
        [box[0]]
        + [
            (max(b[2] for b in extents[col - 1]) + min(b[0] for b in extents[col])) / 2
            for col in range(1, cols)
        ]
        + [box[2]]
    )
    if any(b - a < 3 for a, b in zip(edges, edges[1:])):
        return item
    chars = [
        c
        for c in page.chars
        if c["text"].strip()
        and box[0] <= (c["x0"] + c["x1"]) / 2 <= box[2]
        and box[1] <= (c["top"] + c["bottom"]) / 2 <= box[3]
    ]
    if (
        not chars
        or len(chars) > 50000
        or any(
            not c.get("upright")
            or any(
                not isinstance(c.get(k), (int, float)) or not math.isfinite(c[k])
                for k in ["x0", "x1", "top", "bottom", "size"]
            )
            for c in chars
        )
    ):
        return item
    h = median(c["bottom"] - c["top"] for c in chars)
    if not 3 <= h <= 30:
        return item
    word_columns = {}
    for word in page.extract_words(x_tolerance=1.5, y_tolerance=2, return_chars=True):
        center = (word["x0"] + word["x1"]) / 2
        for col, (left, right) in enumerate(zip(edges, edges[1:])):
            if left <= center < right:
                for ch in word["chars"]:
                    word_columns[id(ch)] = col
                break
    lines = []
    for group in cluster_objects(
        chars, lambda c: (c["top"] + c["bottom"]) / 2, min(2.5, h * 0.25)
    ):
        parts = [
            [c for c in group if word_columns.get(id(c)) == col] for col in range(cols)
        ]
        values = [
            extract_text(part, x_tolerance=1.5, y_tolerance=2) if part else ""
            for part in parts
        ]
        dense = (
            bool(values[0])
            and any(ch.isalpha() for ch in values[0])
            and sum(numeric(v) for v in values[1:]) >= 0.8 * (cols - 1)
            and all(not v or numeric(v) for v in values[1:])
        )
        # A missing boundary cannot turn two independently spaced numbers into
        # one literal. Permit only ordinary spaces within a compact numeric run.
        compact = all(
            all(
                b["x0"] - a["x1"] <= h * 0.65
                for a, b in zip(
                    sorted(part, key=lambda c: c["x0"]),
                    sorted(part, key=lambda c: c["x0"])[1:],
                )
            )
            for part in parts[1:]
        )
        lines.append(
            dict(
                chars=group,
                parts=parts,
                values=values,
                y=median((c["top"] + c["bottom"]) / 2 for c in group),
                dense=dense and compact,
            )
        )
    indices = [i for i, line in enumerate(lines) if line["dense"]]
    if len(indices) < 15 or indices != list(range(indices[0], indices[-1] + 1)):
        return item
    body = [lines[i] for i in indices]
    gaps = [b["y"] - a["y"] for a, b in zip(body, body[1:])]
    pitch = median(gaps)
    if not h * 0.8 <= pitch <= h * 2 or any(
        abs(gap - pitch) > pitch * 0.2 for gap in gaps
    ):
        return item
    bodytop = min(c["top"] for c in body[0]["chars"])
    bodybottom = max(c["bottom"] for c in body[-1]["chars"])
    before = [
        c
        for c in cells
        if c.get("bbox")
        and c["text"].strip()
        and model_box(c["bbox"], page)[3] <= bodytop + 1
    ]
    after = [
        c
        for c in cells
        if c.get("bbox")
        and c["text"].strip()
        and model_box(c["bbox"], page)[1] >= bodybottom - 1
    ]
    if after:
        return item
    header_rows = max((c["end_row_offset_idx"] for c in before), default=0)
    if not 1 <= header_rows <= 5:
        return item
    headers = [c for c in cells if c["start_row_offset_idx"] < header_rows]
    if any(
        c["end_row_offset_idx"] > header_rows or (c["text"].strip() and c not in before)
        for c in headers
    ):
        return item
    # A closed multiline cell is not a set of separate records.
    physical = physical_page(page)
    horizontal = [
        e
        for e in physical.edges
        if e["orientation"] == "h"
        and min(e["x1"], box[2]) - max(e["x0"], box[0]) >= (box[2] - box[0]) * 0.8
    ]
    vertical = [
        e
        for e in physical.edges
        if e["orientation"] == "v"
        and e["top"] <= body[0]["y"]
        and e["bottom"] >= body[-1]["y"]
    ]
    if (
        len(vertical) >= 2
        and any(bodytop - pitch <= e["top"] <= bodytop for e in horizontal)
        and any(bodybottom <= e["top"] <= bodybottom + pitch for e in horizontal)
    ):
        if any(
            not any(a["y"] < e["top"] < b["y"] for e in horizontal)
            for a, b in zip(body, body[1:])
        ):
            return item
    source = Counter(
        ch
        for line in body
        for c in line["chars"]
        for ch in c["text"]
        if not ch.isspace()
    )
    actual = Counter(
        ch
        for line in body
        for value in line["values"]
        for ch in value
        if not ch.isspace()
    )
    if source != actual:
        return item
    result = copy.deepcopy(item)
    new = copy.deepcopy(headers)
    for row, line in enumerate(body, header_rows):
        for col, (value, part) in enumerate(zip(line["values"], line["parts"])):
            bbox = (
                [
                    min(c["x0"] for c in part),
                    min(c["top"] for c in part),
                    max(c["x1"] for c in part),
                    max(c["bottom"] for c in part),
                ]
                if part
                else [edges[col], line["y"] - h / 2, edges[col + 1], line["y"] + h / 2]
            )
            new.append(
                dict(
                    start_row_offset_idx=row,
                    end_row_offset_idx=row + 1,
                    start_col_offset_idx=col,
                    end_col_offset_idx=col + 1,
                    row_span=1,
                    col_span=1,
                    text=value,
                    bbox=local_box(bbox, page),
                    column_header=False,
                    row_header=col == 0,
                    row_section=False,
                )
            )

    def signature(entries):
        return sorted(
            (
                c["start_row_offset_idx"],
                c["start_col_offset_idx"],
                c["row_span"],
                c["col_span"],
                c["text"],
            )
            for c in entries
        )

    if signature(new) == signature(cells) and data["num_rows"] == header_rows + len(
        body
    ):
        return item
    result["data"]["table_cells"] = new
    result["data"]["num_rows"] = header_rows + len(body)
    return result
