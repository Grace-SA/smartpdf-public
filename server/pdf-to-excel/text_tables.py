"""Conservative borderless table detection from repeated, separated columns.

Paragraph word starts are not column boundaries. A candidate needs at least
three consecutive rows with matching column starts and visible inter-cell gaps.
"""

from statistics import median
import re


def conservative_aligned_tables(page):
    numeric = re.compile(r"[+\-−($€£¥]?\d[\d\s.,%()\-]*")
    return [
        table
        for table in aligned_tables(page)
        if any(
            cell["r"] == 0 and any(char.isalpha() for char in cell["text"])
            for cell in table["cells"]
        )
        and sum(
            bool(numeric.fullmatch(cell["text"].strip())) for cell in table["cells"]
        )
        >= max(2, len(table["cells"]) * 0.25)
    ]


def aligned_tables(page, excluded=()):
    words = page.extract_words(x_tolerance=2, y_tolerance=3)
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
