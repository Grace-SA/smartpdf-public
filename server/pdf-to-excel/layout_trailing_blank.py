"""Retain visible ruled blank rows lost when native empty rows were trimmed."""

from copy import deepcopy
import math


def cells(table):
    return {(c["r"], c["c"], c["rs"], c["cs"]): c["text"] for c in table["cells"]}


def recover(table, page, table_from_pdf):
    from layout_tables import physical_page, visible_box

    box = table.get("bbox")
    widths = table["widths"]
    heights = table["heights"]
    if (
        getattr(page, "rotation", 0)
        or not box
        or len(box) != 4
        or not 2 <= len(widths) <= 40
        or not 2 <= len(heights) <= 300
        or not all(
            isinstance(v, (int, float)) and math.isfinite(v)
            for v in list(box) + widths + heights
        )
        or any(v <= 0 for v in widths + heights)
        or abs(sum(widths) - (box[2] - box[0])) > 3
        or box[3] - box[1] - sum(heights) <= 3
    ):
        return table
    options = []
    view = visible_box(page)
    if not (
        view[0] <= box[0] < box[2] <= view[2] and view[1] <= box[1] < box[3] <= view[3]
    ):
        return table
    physical = physical_page(page.crop(tuple(view)))
    for grid in physical.find_tables():
        if any(abs(a - b) > 0.5 for a, b in zip(grid.bbox, box)):
            continue
        candidate = table_from_pdf(grid, preserve_empty_rows=True)
        if (
            not candidate
            or not candidate.get("closedGrid")
            or len(candidate["widths"]) != len(widths)
            or not len(heights) < len(candidate["heights"]) <= len(heights) + 4
        ):
            continue
        prefix = dict(
            candidate, cells=[c for c in candidate["cells"] if c["r"] < len(heights)]
        )
        suffix = [c for c in candidate["cells"] if c["r"] >= len(heights)]
        if (
            cells(prefix) != cells(table)
            or not suffix
            or any(c["text"].strip() for c in suffix)
        ):
            continue
        options.append(candidate)
    if len(options) != 1:
        return table
    candidate = options[0]
    result = deepcopy(table)
    old = {(c["r"], c["c"], c["rs"], c["cs"]): c for c in table["cells"]}
    result.update(
        widths=candidate["widths"],
        heights=candidate["heights"],
        cells=[
            deepcopy(old.get((c["r"], c["c"], c["rs"], c["cs"]), c))
            for c in candidate["cells"]
        ],
    )
    result["sourceTrailingBlankRows"] = len(candidate["heights"]) - len(heights)
    return result
