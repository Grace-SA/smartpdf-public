"""Ignore overprinted blanks within verified compact numeric/date glyph runs."""

from collections import defaultdict
import math
import re
from statistics import median
from pdfplumber.utils import cluster_objects


def visible_glyphs(chars):
    """Return original glyph objects except demonstrably overprinted blanks.

    A whitespace glyph is invisible, but extractors can interleave its position
    with a later number drawn on top. Only remove an upright blank whose
    horizontal centre falls inside a visible glyph with at least 80% vertical
    overlap. Oversized, nonfinite, skewed and rotated glyphs stay unchanged.
    """

    def eligible(ch):
        coordinates = [ch.get(k, math.nan) for k in ("x0", "x1", "top", "bottom")]
        if not all(
            isinstance(v, (int, float)) and math.isfinite(v) for v in coordinates
        ):
            return False
        x0, x1, top, bottom = coordinates
        matrix = ch.get("matrix")
        if matrix is not None and (
            len(matrix) != 6
            or any(not math.isfinite(v) for v in matrix)
            or abs(matrix[1]) > 1e-6
            or abs(matrix[2]) > 1e-6
        ):
            return False
        return ch.get("upright", True) and x1 > x0 and 0 < bottom - top <= 72

    # Overhanging letters, Arabic joining and dot leaders may overlap a real
    # word separator. Only a complete, compact numeric/date run is eligible.
    ink = [ch for ch in chars if ch["text"].strip() and eligible(ch)]
    numeric_ids = set()
    if ink:
        tolerance = min(2, median(ch["bottom"] - ch["top"] for ch in ink) * 0.2)
        rows = cluster_objects(
            ink, lambda ch: (ch["top"] + ch["bottom"]) / 2, tolerance
        )
        for row in rows:
            runs = []
            for ch in sorted(row, key=lambda ch: ch["x0"]):
                if (
                    runs
                    and ch["x0"] - runs[-1][-1]["x1"]
                    <= min(
                        ch["bottom"] - ch["top"],
                        runs[-1][-1]["bottom"] - runs[-1][-1]["top"],
                    )
                    * 0.75
                ):
                    runs[-1].append(ch)
                else:
                    runs.append([ch])
            for run in runs:
                text = "".join(ch["text"] for ch in run)
                if text.startswith("(") != text.endswith(")"):
                    continue
                if len(text) >= 3 and re.fullmatch(
                    r"\(?[+−-]?[0-9]+(?:[.,/:-][0-9]+)*%?\)?", text
                ):
                    numeric_ids.update(id(ch) for ch in run)
    bands = defaultdict(list)
    for ch in chars:
        if id(ch) not in numeric_ids:
            continue
        for band in range(
            math.floor(ch["top"] / 16), math.floor(ch["bottom"] / 16) + 1
        ):
            bands[band].append(ch)
    removed = set()
    for ch in chars:
        if ch["text"].strip() or not eligible(ch):
            continue
        x = (ch["x0"] + ch["x1"]) / 2
        y = (ch["top"] + ch["bottom"]) / 2
        if any(
            g["x0"] < x < g["x1"]
            and min(g["bottom"], ch["bottom"]) - max(g["top"], ch["top"])
            >= (ch["bottom"] - ch["top"]) * 0.8
            for g in bands[math.floor(y / 16)]
        ):
            removed.add(id(ch))
    return [ch for ch in chars if id(ch) not in removed]


def without_overprinted_blanks(page):
    if not hasattr(page, "filter") or not hasattr(page, "chars"):
        return page
    chars = page.chars
    visible = visible_glyphs(chars)
    if len(chars) == len(visible):
        return page
    keep = {id(ch) for ch in visible}
    return page.filter(lambda obj: obj.get("object_type") != "char" or id(obj) in keep)
