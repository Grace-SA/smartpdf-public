"""Recover full-width category rows separating otherwise complete ruled grids."""

from statistics import median
import math
from pdfplumber.table import Table
from pdfplumber.utils import extract_text


def restore_fragmented_rows(table, page, table_factory):
    from layout_tables import physical_page, visible_box

    box = table.get("bbox")
    nr, nc = len(table["heights"]), len(table["widths"])
    if (
        getattr(page, "rotation", 0)
        or not box
        or not 3 <= nc <= 40
        or not 3 <= nr <= 300
        or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in box)
    ):
        return table
    physical = physical_page(page.crop(tuple(visible_box(page))))
    finder = physical.debug_tablefinder()
    cells = [
        b
        for b in finder.cells
        if box[0] - 3 <= b[0] < b[2] <= box[2] + 3
        and box[1] - 3 <= b[1] < b[3] <= box[3] + 3
    ]
    if not cells:
        return table
    xs = sorted(set(round(b[k], 2) for b in cells for k in (0, 2)))
    ys = sorted(set(round(b[k], 2) for b in cells for k in (1, 3)))
    if len(xs) != nc + 1 or len(ys) != nr + 1:
        return table
    occupancy = set()
    for b in cells:
        c, ec = xs.index(round(b[0], 2)), xs.index(round(b[2], 2))
        r, er = ys.index(round(b[1], 2)), ys.index(round(b[3], 2))
        area = {(y, x) for y in range(r, er) for x in range(c, ec)}
        if not area or occupancy & area:
            return table
        occupancy.update(area)
    missing = {(r, c) for r in range(nr) for c in range(nc)} - occupancy
    gaps = sorted({r for r, c in missing})
    if not 1 <= len(gaps) <= 4 or missing != {(r, c) for r in gaps for c in range(nc)}:
        return table
    normalized = lambda value: " ".join(value.split())
    populated = {
        (c["r"], c["c"]): normalized(c["text"])
        for c in table["cells"]
        if c["text"].strip()
    }

    def horizontal_rule(y):
        intervals = sorted(
            (e["x0"], e["x1"])
            for e in physical.edges
            if e["orientation"] == "h" and abs(e["top"] - y) <= 1
        )
        reached = xs[0]
        for left, right in intervals:
            if left <= reached + 1:
                reached = max(reached, right)
        return reached >= xs[-1] - 1

    pitch = median(b - a for a, b in zip(ys, ys[1:]))
    for r in gaps:
        if (
            ys[r + 1] - ys[r] > pitch * 2
            or not horizontal_rule(ys[r])
            or not horizontal_rule(ys[r + 1])
            or any(
                e["orientation"] == "v"
                and xs[0] + 2 < e["x0"] < xs[-1] - 2
                and min(e["bottom"], ys[r + 1]) - max(e["top"], ys[r])
                > (ys[r + 1] - ys[r]) * 0.3
                for e in physical.edges
            )
        ):
            return table
        ink = [
            ch
            for ch in physical.chars
            if xs[0] <= (ch["x0"] + ch["x1"]) / 2 < xs[-1]
            and ys[r] <= (ch["top"] + ch["bottom"]) / 2 < ys[r + 1]
        ]
        text = normalized(
            extract_text(ink, x_tolerance=2, y_tolerance=3) if ink else ""
        )
        if (
            not any(ch.isalpha() for ch in text)
            or any(ch.isdigit() for ch in text)
            or populated.get((r, 0)) != text
            or any((r, c) in populated for c in range(1, nc))
        ):
            return table
        cells.append((xs[0], ys[r], xs[-1], ys[r + 1]))
    candidate = table_factory(Table(physical, cells))
    if (
        not candidate
        or not candidate.get("closedGrid")
        or (len(candidate["heights"]), len(candidate["widths"])) != (nr, nc)
        or {
            (c["r"], c["c"]): normalized(c["text"])
            for c in candidate["cells"]
            if c["text"].strip()
        }
        != populated
    ):
        return table
    native = {(c["r"], c["c"]): c for c in candidate["cells"]}
    target_rows = set()
    for cell in table["cells"]:
        if not cell["text"].strip():
            continue
        other = native[(cell["r"], cell["c"])]
        if (cell["rs"], cell["cs"]) == (other["rs"], other["cs"]):
            continue
        if not (
            cell["c"] == 0
            and cell["rs"] == other["rs"] == 1
            and cell["cs"] == 1
            and other["cs"] == nc
        ):
            return table
        target_rows.add(cell["r"])
    if not target_rows:
        return table
    result = []
    for cell in table["cells"]:
        affected = {r for r in target_rows if cell["r"] <= r < cell["r"] + cell["rs"]}
        if not affected:
            result.append(cell)
        elif cell["rs"] != 1:
            return table
        elif cell["text"].strip():
            result.append(dict(cell, cs=nc))
    return dict(table, cells=result)
