"""Reassign a misplaced native dot leader, never repair or infer a number.

Only repeated first-label/first-number pairs with exact source glyph evidence
qualify. A legitimate leading decimal, isolated punctuation, physical separator,
merged/multiline cell or ambiguous geometry is left unchanged.
"""

import math
import re
from collections import Counter, defaultdict
from itertools import pairwise
from numbers import Real
from statistics import median

from layout_tables import physical_page, visible_box


def _finite(values):
    return all(isinstance(v, Real) and math.isfinite(v) for v in values)


def _box(box):
    return (
        isinstance(box, (list, tuple))
        and len(box) == 4
        and _finite(box)
        and box[0] < box[2]
        and box[1] < box[3]
    )


def _compact(text):
    return "".join(text.split())


def recover(table, page):
    """Return a copy only for >=3 nonoverlapping rows sharing the same boundary.

    Call before source typography recovery, which must use the corrected glyph
    bounds. The original table and source PDF bytes are never modified.
    """
    if getattr(page, "rotation", 0) or not table.get("method", "").startswith("layout"):
        return table
    cells = table.get("cells", [])
    indexed = {(c["r"], c["c"]): c for c in cells}
    if len(indexed) != len(cells):
        return table
    pairs = []
    for right in cells:
        left = indexed.get((right["r"], 0))
        if (
            right["c"] != 1
            or left is None
            or any(c.get("rs") != 1 or c.get("cs") != 1 for c in (left, right))
            or any("\n" in c["text"] or "\r" in c["text"] for c in (left, right))
            or not re.fullmatch(r"\.[ \t]+[0-9]+\.[0-9]+", right["text"].strip())
            or not re.search(r"(?:\.[ \t]*){4,}$", left["text"])
            or not any(ch.isalpha() for ch in left["text"])
        ):
            continue
        pairs.append((left, right))
    if not 3 <= len(pairs) <= 200:
        return table
    view = visible_box(page)
    if not _box(view):
        return table
    chars = [c for c in page.chars if c.get("text", "").strip()]
    if len(chars) > 50000 or any(
        not _finite([c.get(k) for k in ("x0", "x1", "top", "bottom")]) for c in chars
    ):
        return table
    bands = defaultdict(list)
    for c in chars:
        bands[math.floor((c["top"] + c["bottom"]) / 32)].append(c)
    verticals = [e for e in physical_page(page).edges if e.get("orientation") == "v"]
    if any(
        not _finite([e.get(k) for k in ("x0", "x1", "top", "bottom")])
        for e in verticals
    ):
        return table

    def glyphs(box):
        selected = [
            c
            for key in range(
                math.floor((box[1] - 0.5) / 16), math.floor((box[3] + 0.5) / 16) + 1
            )
            for c in bands[key]
            if box[0] - 0.1 <= (c["x0"] + c["x1"]) / 2 <= box[2] + 0.1
            and box[1] - 0.5 <= (c["top"] + c["bottom"]) / 2 <= box[3] + 0.5
        ]
        return sorted(selected, key=lambda c: c["x0"])

    candidates = []
    for left, right in pairs:
        boxes = [c.get("sourceTextCandidate") for c in (left, right)]
        if (
            any(
                not _box(b)
                or not (
                    view[0] <= b[0] < b[2] <= view[2]
                    and view[1] <= b[1] < b[3] <= view[3]
                )
                or b[3] - b[1] > 40
                for b in boxes
            )
            or boxes[0][2] >= boxes[1][0]
        ):
            continue
        a, b = map(glyphs, boxes)
        if (
            not a
            or len(b) < 4
            or any(
                _compact(cell["text"]) != "".join(c["text"] for c in group)
                for cell, group in ((left, a), (right, b))
            )
        ):
            continue
        all_chars = a + b
        if (
            any(
                not c.get("upright")
                or not (
                    view[0] <= c["x0"] < c["x1"] <= view[2]
                    and view[1] <= c["top"] < c["bottom"] <= view[3]
                )
                or not c.get("matrix")
                or len(c["matrix"]) != 6
                or not _finite(c["matrix"])
                or c["matrix"][0] <= 0
                or c["matrix"][3] <= 0
                or abs(c["matrix"][1]) > 0.001
                or abs(c["matrix"][2]) > 0.001
                for c in all_chars
            )
            or max(c["top"] for c in all_chars) - min(c["top"] for c in all_chars) > 1
        ):
            continue
        dots = []
        for c in reversed(a):
            if c["text"] != ".":
                break
            dots.append(c)
        dots = list(reversed(dots)) + [b[0]]
        if len(dots) < 5 or b[0]["text"] != "." or not b[1]["text"].isdigit():
            continue
        if any(
            not isinstance(c.get("size"), Real)
            or not math.isfinite(c["size"])
            or not c.get("fontname")
            for c in dots
        ):
            continue
        size = median(c["size"] for c in dots)
        if (
            not 4 <= size <= 24
            or len({c["fontname"] for c in dots}) != 1
            or any(abs(c["size"] - size) > 0.1 for c in dots)
        ):
            continue
        gaps = [y["x0"] - x["x1"] for x, y in pairwise(dots)]
        gap = median(gaps)
        if not 0.5 <= gap <= size or any(
            abs(g - gap) > max(0.3, gap * 0.2) for g in gaps
        ):
            continue
        if b[1]["x0"] - b[0]["x1"] < max(size, 4 * gap):
            continue
        if any(
            dots[-2]["x1"] - 0.1 <= (e["x0"] + e["x1"]) / 2 <= b[0]["x0"] + 0.1
            and min(e["bottom"], b[0]["bottom"]) > max(e["top"], b[0]["top"])
            for e in verticals
        ):
            continue
        new_left = left["text"].rstrip() + " ."
        new_right = right["text"].strip()[1:].lstrip()
        if Counter(_compact(left["text"] + right["text"])) != Counter(
            _compact(new_left + new_right)
        ):
            continue
        candidates.append((left, right, a, b, new_left, new_right))

    groups = []
    for candidate in sorted(candidates, key=lambda c: c[3][0]["x0"]):
        dot = candidate[3][0]
        group = next(
            (
                g
                for g in groups
                if abs(g[0][3][0]["x0"] - dot["x0"]) <= 1
                and abs(
                    g[0][1]["sourceTextCandidate"][2]
                    - candidate[1]["sourceTextCandidate"][2]
                )
                <= 2
            ),
            None,
        )
        if group is None:
            groups.append([candidate])
        else:
            group.append(candidate)
    updates = {}
    for group in groups:
        ordered = sorted(group, key=lambda c: c[3][0]["top"])
        if len(group) < 3 or any(
            a[3][0]["bottom"] > b[3][0]["top"] + 0.1 for a, b in pairwise(ordered)
        ):
            continue
        for left, right, a, b, new_left, new_right in group:
            for cell, source, text in (
                (left, a + b[:1], new_left),
                (right, b[1:], new_right),
            ):
                updates[cell["r"], cell["c"]] = dict(
                    cell,
                    text=text,
                    sourceTextCandidate=[
                        min(c["x0"] for c in source),
                        min(c["top"] for c in source),
                        max(c["x1"] for c in source),
                        max(c["bottom"] for c in source),
                    ],
                )
    if not updates:
        return table
    changed = dict(
        table,
        cells=[updates.get((c["r"], c["c"]), c) for c in cells],
        sourceLeaderBoundary=True,
    )
    if Counter(_compact("".join(c["text"] for c in cells))) != Counter(
        _compact("".join(c["text"] for c in changed["cells"]))
    ):
        return table
    return changed
