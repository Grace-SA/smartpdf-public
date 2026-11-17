"""Collapse model continuation rows only inside a complete physical grid.

Every column keeps its exact ordered words. A continuation can contain text in
only one column, with no numbers, and the physical header must agree verbatim.
"""

import math


def recover(model, native):
    from layout_tables import overlap
    from layout_partition import valid_box

    rows, cols = len(model.get("heights", [])), len(model.get("widths", []))
    if not 3 <= rows <= 100 or not 2 <= cols <= 30 or not valid_box(model.get("bbox")):
        return model

    def matrix(table, *, require_complete):
        nr, nc = len(table["heights"]), len(table["widths"])
        slots = {}
        for cell in table.get("cells", []):
            indices = [cell.get(k) for k in ("r", "c", "rs", "cs")]
            if any(not isinstance(x, int) or isinstance(x, bool) for x in indices):
                return None
            r, c, rs, cs = indices
            if not (0 <= r < nr and 0 <= c < nc and rs == cs == 1):
                return None
            if (r, c) in slots or not isinstance(cell.get("text"), str):
                return None
            slots[r, c] = " ".join(cell["text"].split())
        if require_complete and len(slots) != nr * nc:
            return None
        return [[slots.get((r, c), "") for c in range(nc)] for r in range(nr)]

    old = matrix(model, require_complete=False)
    if old is None:
        return model
    options = []
    for candidate in native:
        nr = len(candidate.get("heights", []))
        box = candidate.get("bbox")
        if (
            not candidate.get("closedGrid")
            or not 2 <= nr < rows
            or rows - nr > 4
            or len(candidate.get("widths", [])) != cols
            or not valid_box(box)
            or overlap(box, model["bbox"]) < 0.95
            or any(
                not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0
                for v in candidate["widths"] + candidate["heights"]
            )
            or abs(sum(candidate["widths"]) - (box[2] - box[0])) > 3
            or abs(sum(candidate["heights"]) - (box[3] - box[1])) > 3
        ):
            continue
        new = matrix(candidate, require_complete=True)
        if new is None or new[0] != old[0]:
            continue
        # Bound the search to four removed rows, with at most two continuation
        # lines per physical row. Require one unique complete row assignment.
        paths = [(1, 0)]
        for target in new[1:]:
            following = []
            for start, removed in paths:
                for end in range(start + 1, min(rows, start + 3) + 1):
                    if removed + end - start - 1 > 4:
                        continue
                    combined = old[start].copy()
                    valid = True
                    continuation_column = None
                    for row in old[start + 1 : end]:
                        content = [(c, value) for c, value in enumerate(row) if value]
                        if len(content) != 1:
                            valid = False
                            break
                        col, value = content[0]
                        if (
                            not combined[col]
                            or not any(ch.isalpha() for ch in value)
                            or any(ch.isdigit() for ch in value)
                            or (
                                continuation_column is not None
                                and col != continuation_column
                            )
                        ):
                            valid = False
                            break
                        continuation_column = col
                        combined[col] += " " + value
                    if valid and combined == target:
                        following.append((end, removed + end - start - 1))
            paths = following
            if len(paths) > 32:
                paths = []
                break
        if sum(end == rows and removed == rows - nr for end, removed in paths) == 1:
            options.append(candidate)
    return options[0] if len(options) == 1 else model
