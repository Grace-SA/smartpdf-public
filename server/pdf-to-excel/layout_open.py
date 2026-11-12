"""Recover open table borders from repeated, aligned physical rule ends."""

from collections import Counter
import re
from statistics import median

from pdfplumber.utils import cluster_list


def compatible(item, table):
    data = item["data"]
    cells = data["table_cells"]
    if len(table["heights"]) != data["num_rows"] or not (
        data["num_cols"] <= len(table["widths"]) <= data["num_cols"] + 1
    ):
        return False
    old_merges = sum(
        bool(c["text"].strip()) and (c["row_span"] > 1 or c["col_span"] > 1)
        for c in cells
    )
    new_merges = sum(
        bool(c["text"].strip()) and (c["rs"] > 1 or c["cs"] > 1) for c in table["cells"]
    )
    if new_merges < old_merges:
        return False
    if len(table["widths"]) > data["num_cols"] and any(
        sum(bool(c["text"].strip()) and c["c"] == col for c in table["cells"]) < 2
        for col in range(len(table["widths"]))
    ):
        return False

    def numeric(text):
        return re.fullmatch(r"[\d.,%()+−–—\-]+", text.strip()) and any(
            ch.isdigit() for ch in text
        )

    before = Counter("".join(c["text"].split()) for c in cells if numeric(c["text"]))
    after = Counter(
        "".join(c["text"].split()) for c in table["cells"] if numeric(c["text"])
    )
    return not (before - after)


def recover_open_grid(item, page):
    from layout_tables import model_box, physical_page, visible_box
    from layout_grid import recover_source_grid

    box = model_box(item["prov"][0]["bbox"], page)
    left, top, right, bottom = box
    view = visible_box(page)
    region = (
        max(view[0], left - 3),
        max(view[1], top - 3),
        min(view[2], right + 3),
        min(view[3], bottom + 3),
    )
    if region[0] >= region[2] or region[1] >= region[3]:
        return None
    local = physical_page(page.crop(region))
    horizontal = [
        e
        for e in local.edges
        if e["orientation"] == "h"
        and top - 3 <= e["top"] <= bottom + 3
        and e["x1"] - e["x0"] >= (right - left) * 0.8
    ]
    vertical = [
        e
        for e in local.edges
        if e["orientation"] == "v"
        and left - 3 <= e["x0"] <= right + 3
        and top - 3 <= e["top"] <= bottom + 3
    ]
    if len(horizontal) < 4 or len(vertical) < 3:
        return None
    groups = cluster_list([e["x0"] for e in horizontal], 3) + cluster_list(
        [e["x1"] for e in horizontal], 3
    )
    xs = [median(group) for group in groups if len(group) >= 4]
    xs = [x for x in xs if abs(x - left) < 10 or abs(x - right) < 10]
    if not xs:
        return None
    # Crop first: an inferred border must not join two tables through the prose
    # between them. Only physical rule ends may extend the outside borders.
    grids = local.find_tables(dict(explicit_vertical_lines=xs))
    table = recover_source_grid(item, page, grids=grids, allow_blank_stub=True)
    return table if table and compatible(item, table) else None
