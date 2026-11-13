"""Recover sectioned numeric records from complete native lines and source rules.

An isolated experiment: no document IDs, expected rows, or reference values.
"""

from collections import Counter, defaultdict
from copy import deepcopy
from statistics import median
import math
import re

from pdfplumber.utils import cluster_objects, extract_text
from layout_tables import model_box, local_box, physical_page, visible_box


def number(text):
    value = re.sub(r"\s+", "", text)
    return bool(
        re.fullmatch(
            r"(?:Ref\.|[—–-]|[+−–-]?(?:\d[\d.,]*|\.\d+)(?:%|\*{1,3}|†|‡)?|\([\d.,]+(?:[–−-][\d.,]+)?\))",
            value,
        )
    )


def recover(item, page):
    data = item["data"]
    cols = data["num_cols"]
    cells = data["table_cells"]
    if (
        not hasattr(page, "extract_words")
        or getattr(page, "rotation", 0)
        or not 5 <= cols <= 30
        or not 20 <= data["num_rows"] <= 300
    ):
        return item
    header_end = max(
        (c["end_row_offset_idx"] for c in cells if c.get("column_header")), default=0
    )
    if not 1 <= header_end <= 4:
        return item
    headers = [c for c in cells if c["start_row_offset_idx"] < header_end]
    body = [c for c in cells if c["start_row_offset_idx"] >= header_end]
    if any(c["end_row_offset_idx"] > header_end for c in headers):
        return item
    box = model_box(item["prov"][0]["bbox"], page)
    view = visible_box(page)
    if not all(math.isfinite(v) for v in box) or not (
        view[0] <= box[0] < box[2] <= view[2] and view[1] <= box[1] < box[3] <= view[3]
    ):
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
    hbottom = max(b[3] for b in hb)
    btop = min(b[1] for b in bb)
    if hbottom > btop + 1:
        return item
    physical = physical_page(page)
    full = []
    for group in cluster_objects(
        [e for e in physical.edges if e["orientation"] == "h"], lambda e: e["top"], 0.5
    ):
        merged = []
        for edge in sorted(group, key=lambda e: e["x0"]):
            if merged and edge["x0"] <= merged[-1]["x1"] + 1:
                merged[-1]["x1"] = max(merged[-1]["x1"], edge["x1"])
            else:
                merged.append(dict(edge))
        full.extend(
            e
            for e in merged
            if min(e["x1"], box[2]) - max(e["x0"], box[0]) >= 0.95 * (box[2] - box[0])
        )
    starts = [e["top"] for e in full if hbottom - 1 <= e["top"] <= btop]
    ends = [
        e["top"] for e in full if max(b[3] for b in bb) - 1 <= e["top"] <= box[3] + 4
    ]
    if not starts or not ends:
        return item
    top, bottom = max(starts), min(ends)
    if any(
        e["orientation"] == "v" and e["top"] <= top + 1 and e["bottom"] >= bottom - 1
        for e in physical.edges
    ):
        return item
    extents = defaultdict(list)
    for c in body:
        col = c["start_col_offset_idx"]
        if (
            c.get("bbox")
            and c["col_span"] == 1
            and c["text"].strip()
            and (col == 0 or number(c["text"]))
        ):
            extents[col].append(model_box(c["bbox"], page))
    if any(len(extents[col]) < 10 for col in range(cols)):
        return item
    cuts = (
        [box[0]]
        + [
            (max(b[2] for b in extents[col - 1]) + min(b[0] for b in extents[col])) / 2
            for col in range(1, cols)
        ]
        + [box[2]]
    )
    if any(b - a < 5 for a, b in zip(cuts, cuts[1:])):
        return item
    chars = [
        c
        for c in page.chars
        if c["text"].strip()
        and box[0] <= (c["x0"] + c["x1"]) / 2 <= box[2]
        and top < (c["top"] + c["bottom"]) / 2 < bottom
    ]
    if (
        not chars
        or len(chars) > 50000
        or any(
            not c.get("upright")
            or any(
                not isinstance(c.get(k), (float, int)) or not math.isfinite(c[k])
                for k in ["x0", "x1", "top", "bottom", "size"]
            )
            for c in chars
        )
    ):
        return item
    height = median(c["bottom"] - c["top"] for c in chars)
    if not 4 <= height <= 20:
        return item
    admitted = {id(c) for c in chars}
    word_columns = {}
    for word in page.extract_words(x_tolerance=1.5, y_tolerance=2, return_chars=True):
        active = [c for c in word["chars"] if c["text"].strip()]
        if not active or not any(id(c) in admitted for c in active):
            continue
        if any(id(c) not in admitted for c in active):
            return item
        center = (word["x0"] + word["x1"]) / 2
        col = next(
            (i for i, (l, r) in enumerate(zip(cuts, cuts[1:])) if l <= center < r), None
        )
        if (
            col is None
            or word["x0"] < cuts[col] - height * 0.3
            or word["x1"] > cuts[col + 1] + height * 0.3
        ):
            return item
        word_columns.update({id(c): col for c in active})
    if set(word_columns) != admitted:
        return item
    lines = []
    for group in cluster_objects(
        chars, lambda c: (c["top"] + c["bottom"]) / 2, min(2, height * 0.25)
    ):
        parts = [
            [c for c in group if word_columns[id(c)] == col] for col in range(cols)
        ]
        values = [
            extract_text(part, x_tolerance=1.5, y_tolerance=2) if part else ""
            for part in parts
        ]
        if not values[0] or any(v and not number(v) for v in values[1:]):
            return item
        dense = sum(bool(v) for v in values[1:]) >= 0.8 * (cols - 1)
        if not dense and any(values[1:]):
            return item
        lines.append(
            dict(
                parts=parts,
                values=values,
                dense=dense,
                y=median((c["top"] + c["bottom"]) / 2 for c in group),
                x=min(c["x0"] for c in parts[0]),
                fonts={c["fontname"] for c in parts[0]},
            )
        )
    if sum(l["dense"] for l in lines) < 15 or not lines[-1]["dense"]:
        return item
    rows = []
    sections = continuations = 0
    for i, line in enumerate(lines):
        if line["dense"]:
            rows.append(line)
            continue
        previous = rows[-1] if rows else None
        bold = all(any(s in n.lower() for s in ["bold", "demi"]) for n in line["fonts"])
        following = lines[i + 1] if i + 1 < len(lines) else None
        outdent = previous and line["x"] < previous["x"] - height * 0.4
        section = (
            bold
            or previous is None
            or outdent
            or (
                not previous["dense"]
                and following
                and following["x"] > line["x"] + height * 0.4
            )
        )
        if section:
            sections += 1
            rows.append(line)
        elif (
            previous
            and previous["dense"]
            and 0 < line["y"] - previous["y"] <= height * 1.2
            and line["x"] >= previous["x"] - height * 0.15
            and line["fonts"] == previous["fonts"]
        ):
            previous["parts"][0].extend(line["parts"][0])
            previous["values"][0] += "\n" + line["values"][0]
            continuations += 1
        else:
            return item
    if sections < 2:
        return item
    source = Counter(ch for c in chars for ch in c["text"] if not ch.isspace())
    actual = Counter(
        ch
        for row in rows
        for value in row["values"]
        for ch in value
        if not ch.isspace()
    )
    if source != actual:
        return item
    result = deepcopy(item)
    updated = deepcopy(headers)
    for r, row in enumerate(rows, header_end):
        for col, (value, part) in enumerate(zip(row["values"], row["parts"])):
            bounds = (
                [
                    min(c["x0"] for c in part),
                    min(c["top"] for c in part),
                    max(c["x1"] for c in part),
                    max(c["bottom"] for c in part),
                ]
                if part
                else [
                    cuts[col],
                    row["y"] - height / 2,
                    cuts[col + 1],
                    row["y"] + height / 2,
                ]
            )
            updated.append(
                dict(
                    start_row_offset_idx=r,
                    end_row_offset_idx=r + 1,
                    start_col_offset_idx=col,
                    end_col_offset_idx=col + 1,
                    row_span=1,
                    col_span=1,
                    text=value,
                    bbox=local_box(bounds, page),
                    column_header=False,
                    row_header=col == 0,
                    row_section=False,
                )
            )
    result["data"].update(table_cells=updated, num_rows=header_end + len(rows))
    return result
