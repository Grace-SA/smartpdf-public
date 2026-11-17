"""Separate an above-grid unit from a clipped header using native rules.

Only a uniquely bounded open grid with every body cell unchanged is eligible.
The removed prefix must be independently visible immediately above that grid.
"""

from copy import deepcopy
from statistics import median

from pdfplumber.utils import extract_text


def recover(table, page, factory):
    from layout_tables import physical_page, visible_box
    from layout_partition import valid_box
    from layout_columns import continuous_cuts

    rows, cols = len(table.get("heights", [])), len(table.get("widths", []))
    box = table.get("bbox")
    if (
        getattr(page, "rotation", 0)
        or not 4 <= rows <= 100
        or not 2 <= cols <= 20
        or not valid_box(box)
        or len(page.chars) > 30000
    ):
        return table
    if any(c.get("rs") != 1 or c.get("cs") != 1 for c in table["cells"]):
        return table
    view = visible_box(page)
    bounds = (
        max(view[0], box[0] - 3),
        max(view[1], box[1] - 3),
        min(view[2], box[2] + 3),
        min(view[3], box[3] + 3),
    )
    if not valid_box(bounds):
        return table
    local = physical_page(page.crop(bounds))
    horizontal = [
        e
        for e in local.edges
        if e["orientation"] == "h" and e["x1"] - e["x0"] >= (box[2] - box[0]) * 0.9
    ]
    if not rows <= len(horizontal) <= 500:
        return table
    left, right = median(e["x0"] for e in horizontal), median(
        e["x1"] for e in horizontal
    )
    if max(abs(left - box[0]), abs(right - box[2])) > 3 or any(
        abs(e["x0"] - left) > 1 or abs(e["x1"] - right) > 1 for e in horizontal
    ):
        return table
    grids = local.find_tables(dict(explicit_vertical_lines=[left, right]))
    grids = [
        g
        for g in grids
        if len(g.rows) == rows
        and len(g.columns) == cols
        and abs(g.bbox[0] - left) < 1
        and abs(g.bbox[2] - right) < 1
    ]
    if len(grids) != 1:
        return table
    grid = grids[0]
    cuts = continuous_cuts(local, grid.bbox)
    interior = [x for x in cuts if left + 2 < x < right - 2]
    if len(interior) != cols - 1:
        return table
    candidate = factory(grid)
    if not candidate or not candidate.get("closedGrid"):
        return table
    if any(c["rs"] != 1 or c["cs"] != 1 for c in candidate["cells"]):
        return table
    norm = lambda value: " ".join(value.split())
    old = {(c["r"], c["c"]): norm(c["text"]) for c in table["cells"]}
    new = {(c["r"], c["c"]): norm(c["text"]) for c in candidate["cells"]}
    if len(old) != len(table["cells"]) or len(new) != rows * cols:
        return table
    if any(
        old.get((r, c), "") != new[r, c] for r in range(1, rows) for c in range(cols)
    ):
        return table
    changed = [c for c in range(cols) if old.get((0, c), "") != new[0, c]]
    if (
        len(changed) != 1
        or sum(bool(new[r, c]) for r in range(1, rows) for c in range(cols)) < rows
    ):
        return table
    col = changed[0]
    pitch = median(candidate["heights"])
    if not 0 < grid.bbox[1] - box[1] <= pitch or abs(grid.bbox[3] - box[3]) > 3:
        return table
    xs = [left, *interior, right]
    above = [
        ch
        for ch in page.chars
        if ch["text"].strip()
        and xs[col] <= (ch["x0"] + ch["x1"]) / 2 < xs[col + 1]
        and box[1] - 1 <= (ch["top"] + ch["bottom"]) / 2 < grid.bbox[1]
    ]
    if not above or any(not ch.get("upright") for ch in above):
        return table
    prefix = norm(extract_text(above, x_tolerance=2, y_tolerance=3))
    before, after = old.get((0, col), ""), new[0, col]
    if not prefix or len(prefix) > 20 or not before.startswith(prefix + " "):
        return table
    suffix = before[len(prefix) + 1 :]
    if (
        len(suffix.split()) < 2
        or not any(c.isalpha() for c in suffix)
        or not after.endswith(" " + suffix)
    ):
        return table
    added = after[: -(len(suffix) + 1)]
    if not any(c.isalpha() for c in added) or any(c.isdigit() for c in prefix + added):
        return table
    # Physical bounds keep the removed outside unit available to page_context.
    cells = deepcopy(table["cells"])
    for cell in cells:
        if (cell["r"], cell["c"]) == (0, col):
            cell["text"] = after
            cell["sourceTextCandidate"] = [
                xs[col],
                grid.bbox[1],
                xs[col + 1],
                grid.bbox[1] + candidate["heights"][0],
            ]
    return dict(
        table,
        cells=cells,
        bbox=list(grid.bbox),
        widths=candidate["widths"],
        heights=candidate["heights"],
    )
