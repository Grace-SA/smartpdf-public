"""Conservative borderless table detection from repeated, separated columns.

Paragraph word starts are not column boundaries. A candidate needs at least
three consecutive rows with matching column starts and visible inter-cell gaps.
"""

from statistics import median
import re

NUMERIC = re.compile(r"[+\-−($€£¥]?\d[\d\s.,%()\-]*")


def numeric_page_tables(page):
    """Headerless numeric pages require complete, repeated columns without graphics.

    Persistent wide gutters divide independent side-by-side tables before row
    grouping, so a shorter table cannot cut a longer neighbour into fragments.
    """
    if any(getattr(page, key, []) for key in ("images", "lines", "rects", "curves")):
        return []
    words = page.extract_words(x_tolerance=2, y_tolerance=3)
    if len(words) < 15 or any(not NUMERIC.fullmatch(w["text"]) for w in words):
        return []
    bands = []
    for word in sorted(words, key=lambda w: w["x0"]):
        if bands and word["x0"] <= bands[-1][1] + 4:
            bands[-1][1] = max(bands[-1][1], word["x1"])
        else:
            bands.append([word["x0"], word["x1"]])
    if len(bands) < 3:
        return []
    gaps = [right[0] - left[1] for left, right in zip(bands, bands[1:])]
    # A split must be substantially wider than ordinary column separation.
    cuts = [
        (bands[i][1] + bands[i + 1][0]) / 2
        for i, gap in enumerate(gaps)
        if gap >= max(48, median(gaps) * 2.5)
    ]
    bounds = [float("-inf"), *cuts, float("inf")]
    tables = []
    for left, right in zip(bounds, bounds[1:]):
        region = [w for w in words if left <= w["x0"] < right]
        found = aligned_words(region)
        if (
            not found
            or any(len(t["widths"]) < 3 or len(t["heights"]) < 5 for t in found)
            or sum(len(t["cells"]) for t in found) != len(region)
        ):
            return []
        tables.extend(found)
    for table in tables:
        table["headerRows"] = 0
    return tables


def conservative_aligned_tables(page):
    numeric_tables = numeric_page_tables(page)
    if numeric_tables:
        return numeric_tables
    return [
        table
        for table in aligned_tables(page)
        if any(
            cell["r"] == 0 and any(char.isalpha() for char in cell["text"])
            for cell in table["cells"]
        )
        and sum(
            bool(NUMERIC.fullmatch(cell["text"].strip())) for cell in table["cells"]
        )
        >= max(2, len(table["cells"]) * 0.25)
    ]


def aligned_tables(page, excluded=()):
    words = page.extract_words(x_tolerance=2, y_tolerance=3)
    return aligned_words(words, excluded)


def aligned_words(words, excluded=()):
    lines = []
    for word in sorted(words, key=lambda w: ((w["top"] + w["bottom"]) / 2, w["x0"])):
        cx = (word["x0"] + word["x1"]) / 2
        cy = (word["top"] + word["bottom"]) / 2
        if any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in excluded):
            continue
        if lines and abs(cy - lines[-1]["center"]) <= 3:
            lines[-1]["words"].append(word)
        else:
            lines.append({"center": cy, "words": [word]})

    rows = []
    for line in lines:
        segments = []
        for word in sorted(line["words"], key=lambda w: w["x0"]):
            if segments and word["x0"] - segments[-1][-1]["x1"] < 12:
                segments[-1].append(word)
            else:
                segments.append([word])
        rows.append(
            {
                "segments": segments,
                "top": min(w["top"] for w in line["words"]),
                "bottom": max(w["bottom"] for w in line["words"]),
            }
        )

    groups = []
    current = []

    def flush():
        if len(current) >= 3:
            groups.append(current.copy())
        current.clear()

    for row in rows:
        if len(row["segments"]) < 2:
            flush()
            continue
        if current:
            prior = current[-1]
            starts = [
                median(r["segments"][c][0]["x0"] for r in current)
                for c in range(len(prior["segments"]))
            ]
            matches = len(row["segments"]) == len(starts) and all(
                abs(segment[0]["x0"] - start) <= 5
                for segment, start in zip(row["segments"], starts)
            )
            nearby = row["top"] - prior["bottom"] <= max(
                40, 3 * (prior["bottom"] - prior["top"])
            )
            if not matches or not nearby:
                flush()
        current.append(row)
    flush()

    tables = []
    for group in groups:
        columns = len(group[0]["segments"])
        starts = [min(r["segments"][c][0]["x0"] for r in group) for c in range(columns)]
        ends = [max(r["segments"][c][-1]["x1"] for r in group) for c in range(columns)]
        # No inferred boundary may cut through a source word or another column.
        if any(ends[c] + 4 > starts[c + 1] for c in range(columns - 1)):
            continue
        xs = (
            [starts[0] - 2]
            + [(ends[c - 1] + starts[c]) / 2 for c in range(1, columns)]
            + [ends[-1] + 2]
        )
        ys = (
            [group[0]["top"] - 2]
            + [
                (group[r - 1]["bottom"] + group[r]["top"]) / 2
                for r in range(1, len(group))
            ]
            + [group[-1]["bottom"] + 2]
        )
        cells = [
            {
                "r": r,
                "c": c,
                "rs": 1,
                "cs": 1,
                "text": " ".join(w["text"] for w in segment),
            }
            for r, row in enumerate(group)
            for c, segment in enumerate(row["segments"])
        ]
        tables.append(
            {
                "widths": [b - a for a, b in zip(xs, xs[1:])],
                "heights": [b - a for a, b in zip(ys, ys[1:])],
                "cells": cells,
                "method": "aligned",
                "bbox": [xs[0], ys[0], xs[-1], ys[-1]],
            }
        )
    return tables
