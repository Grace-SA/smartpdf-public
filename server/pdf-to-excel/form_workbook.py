"""Keep native form geometry and readable table widths in a shared worksheet."""

from copy import deepcopy
from itertools import accumulate
import math
from layout_typography import readable_header_widths


def shared_columns(tables, layout, limit):
    if layout != "single" or not any(t.get("coordinateGrid") for t in tables):
        return tables
    result = []
    for source in tables:
        if source.get("coordinateGrid"):
            result.append(source)
            continue
        table = deepcopy(source)
        minimum = 3 if table.get("sourceGeometry") else 8
        widths = [
            min(80, max(minimum, width / 5.25)) * 5.25
            for width in readable_header_widths(table)
        ]
        if any(not math.isfinite(w) or w <= 0 for w in widths):
            raise ValueError("Invalid table dimensions")
        unit = 1.5
        edges = [round(x / unit) for x in accumulate(widths, initial=0)]
        if edges[-1] > 16384 or edges[-1] * len(table["heights"]) > limit:
            raise ValueError(
                "Combining forms and tables exceeds the worksheet budget. Use separate worksheets."
            )
        for cell in table["cells"]:
            start, end = edges[cell["c"]], edges[cell["c"] + cell["cs"]]
            cell["c"], cell["cs"] = start, end - start
        table.update(widths=[unit] * edges[-1], coordinateColumns=True)
        result.append(table)
    if sum(len(t["widths"]) * len(t["heights"]) for t in result) > limit:
        raise ValueError(
            "Combining forms and tables exceeds the worksheet budget. Use separate worksheets."
        )
    return result


def form_preview(table):
    lines = {}
    for cell in sorted(table["cells"], key=lambda c: (c["r"], c["c"])):
        if cell["text"].strip():
            lines.setdefault(cell["r"], []).append(cell["text"])
    return [[" ".join(values)[:1000]] for values in list(lines.values())[:12]]
