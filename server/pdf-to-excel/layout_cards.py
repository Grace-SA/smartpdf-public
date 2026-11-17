"""Recover closed repeated record cards while ignoring smaller internal frames.

A uniform grid with at least three columns, five rows, and three source labels
shared by every card is required. Source baseline order and all characters are
preserved. This fallback never receives reference annotations.
"""

import re
from collections import Counter
from statistics import median
from layout_tables import physical_page, visible_box
from pdfplumber.utils import cluster_objects, extract_text


def recover_card_tables(page, table_from_pdf):
    page = physical_page(page.crop(tuple(visible_box(page))))
    result = []
    for grid in page.find_tables({"edge_min_length": min(page.width, page.height) / 6}):
        try:
            t = table_from_pdf(grid)
        except ValueError:
            continue
        if (
            not t
            or not t["closedGrid"]
            or len(t["widths"]) < 3
            or len(t["heights"]) < 5
        ):
            continue
        if any(
            c["rs"] != 1 or c["cs"] != 1 or not c["text"].strip() for c in t["cells"]
        ):
            continue
        if (
            max(t["widths"]) > min(t["widths"]) * 1.1
            or max(t["heights"]) > min(t["heights"]) * 1.1
        ):
            continue
        # Mixed font heights can put a value above its own label in top-sorted text.
        # Align physical baselines inside each closed card before reading left to right.
        for cell in t["cells"]:
            box = grid.rows[cell["r"]].cells[cell["c"]]
            chars = [
                c
                for c in page.chars
                if box[0] <= (c["x0"] + c["x1"]) / 2 < box[2]
                and box[1] <= (c["top"] + c["bottom"]) / 2 < box[3]
            ]
            if not chars or any(not c["upright"] for c in chars):
                return []
            groups = cluster_objects(
                chars, lambda c: c["bottom"], median(c["height"] for c in chars) * 0.35
            )
            lines = []
            for group in groups:
                baseline = median(c["bottom"] for c in group)
                line = [
                    dict(c, top=baseline - 8, bottom=baseline, doctop=baseline - 8)
                    for c in group
                ]
                lines.append(extract_text(line, x_tolerance=2, y_tolerance=3))
            text = "\n".join(lines)
            if Counter("".join(text.split())) != Counter("".join(cell["text"].split())):
                return []
            cell["text"] = text
        labels = [
            set(re.findall(r"(?m)^\s*([A-Za-z][A-Za-z ]{1,24})\s*:", c["text"]))
            for c in t["cells"]
        ]
        common = set.intersection(*labels)
        if len(common) < 3:
            continue
        t.update(method="ruled-cards", headerRows=0, fontSize=7)
        result.append(t)
    return result
