"""Restore empty merged cells only from a complete source grid matching all populated cells."""

import math, re


def restore_blank_merges(table, page, native_extractor):
    from layout_tables import visible_box

    b = table.get("bbox")
    view = visible_box(page)
    if not b or not all(math.isfinite(v) for v in b) or b[0] >= b[2] or b[1] >= b[3]:
        return table
    region = (
        max(view[0], b[0] - 3),
        max(view[1], b[1] - 3),
        min(view[2], b[2] + 3),
        min(view[3], b[3] + 3),
    )
    if region[0] >= region[2] or region[1] >= region[3]:
        return table
    nr, nc = len(table["heights"]), len(table["widths"])
    if (
        page.rotation
        or nr * nc - sum(c["rs"] * c["cs"] for c in table["cells"] if c["text"].strip())
        < 2
    ):
        return table

    def populated(t):
        return {
            (c["r"], c["c"], c["rs"], c["cs"]): re.sub(r"\s+", " ", c["text"]).strip()
            for c in t["cells"]
            if c["text"].strip()
        }

    expected = populated(table)
    options = []
    for candidate in native_extractor(page.crop(region)):
        if (
            not candidate.get("closedGrid")
            or (len(candidate["heights"]), len(candidate["widths"])) != (nr, nc)
            or populated(candidate) != expected
        ):
            continue
        blanks = [
            c
            for c in candidate["cells"]
            if not c["text"].strip() and (c["rs"] > 1 or c["cs"] > 1)
        ]
        if not blanks:
            continue
        cells = list(table["cells"])
        changed = False
        for blank in blanks:
            r, c, rs, cs = (blank[k] for k in ("r", "c", "rs", "cs"))
            target = {(rr, cc) for rr in range(r, r + rs) for cc in range(c, c + cs)}
            members = []
            valid = True
            for cell in cells:
                rr, cc, rrs, ccs = (cell[k] for k in ("r", "c", "rs", "cs"))
                occupied = {
                    (y, x) for y in range(rr, rr + rrs) for x in range(cc, cc + ccs)
                }
                if occupied & target:
                    if not occupied <= target or cell["text"].strip():
                        valid = False
                        break
                    members.append(cell)
            if not valid or (
                len(members) == 1
                and all(members[0][k] == blank[k] for k in ("r", "c", "rs", "cs"))
            ):
                continue
            cells = [v for v in cells if v not in members] + [dict(blank)]
            changed = True
        if changed:
            options.append(dict(table, cells=cells))
    return options[0] if len(options) == 1 else table
