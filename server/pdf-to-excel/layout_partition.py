"""Reassign complete words only inside a uniquely matching closed source grid."""

from collections import Counter
import math


def recover_partition(model, native):
    from layout_tables import overlap

    rows, cols = len(model.get("heights", [])), len(model.get("widths", []))
    box = model.get("bbox")
    if not 2 <= rows <= 300 or not 3 <= cols <= 40 or not valid_box(box):
        return model
    expected = words(model)
    if not expected:
        return model
    options = []
    for candidate in native:
        widths, heights = candidate.get("widths", []), candidate.get("heights", [])
        bounds = candidate.get("bbox")
        if (
            not candidate.get("closedGrid")
            or (len(heights), len(widths)) != (rows, cols)
            or not valid_box(bounds)
            or overlap(bounds, box) < 0.95
            or not all(
                isinstance(v, (int, float)) and math.isfinite(v) and v > 0
                for v in widths + heights
            )
            or abs(sum(widths) - (bounds[2] - bounds[0])) > 3
            or abs(sum(heights) - (bounds[3] - bounds[1])) > 3
        ):
            continue
        occupied = set()
        valid = True
        for cell in candidate.get("cells", []):
            indices = [cell.get(k) for k in ["r", "c", "rs", "cs"]]
            if not all(isinstance(i, int) for i in indices):
                valid = False
                break
            r, c, rs, cs = indices
            if not (0 <= r < r + rs <= rows and 0 <= c < c + cs <= cols):
                valid = False
                break
            area = {(y, x) for y in range(r, r + rs) for x in range(c, c + cs)}
            if occupied & area:
                valid = False
                break
            occupied.update(area)
        if (
            valid
            and len(occupied) == rows * cols
            and words(candidate) == expected
            and row_words(candidate) == row_words(model)
            and protected_cells(candidate) == protected_cells(model)
        ):
            options.append(candidate)
    return options[0] if len(options) == 1 else model


def valid_box(box):
    return bool(
        box
        and len(box) == 4
        and all(isinstance(v, (int, float)) and math.isfinite(v) for v in box)
        and box[0] < box[2]
        and box[1] < box[3]
    )


def words(table):
    # Preserve whole tokens, signs, separators, case and multiplicity. Equal
    # character bags alone could silently turn 12 into 21 or No into On.
    return Counter(
        token for cell in table.get("cells", []) for token in cell["text"].split()
    )


def row_words(table):
    # This path repairs column ownership. It must never turn a valid logical
    # record into a different row merely because their token bags match.
    result = {}
    for cell in table.get("cells", []):
        result.setdefault(cell["r"], Counter()).update(cell["text"].split())
    return {row: tokens for row, tokens in result.items() if tokens}


def protected_cells(table):
    # Existing header labels and horizontal group spans have already been
    # verified by the header pipeline. A broad physical rectangle must not
    # flatten those independent logical headings.
    return sorted(
        (c["r"], c["c"], c["rs"], c["cs"], tuple(c["text"].split()))
        for c in table["cells"]
        if (c["r"] == 0 and c["text"].strip()) or c["cs"] > 1
    )
