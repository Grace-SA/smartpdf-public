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
    removed = overprinted_phrase_blanks(chars, eligible)
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


def overprinted_phrase_blanks(chars, eligible):
    """Ignore an earlier blank-only run underneath a later ordinary phrase.

    This does not remove single spaces between overhanging letters. The later
    phrase must contain its own word separators; all its glyphs stay intact.
    """
    removed = set()
    index = 0
    while index < len(chars):
        start = index
        while index < len(chars) and not chars[index]["text"].strip():
            index += 1
        if index == start:
            index += 1
            continue
        blanks = chars[start:index]
        if not 8 <= len(blanks) <= 512 or not all(eligible(c) for c in blanks):
            continue
        first = blanks[0]
        height = first["bottom"] - first["top"]
        center = (first["top"] + first["bottom"]) / 2
        font = first.get("fontname")
        if not font or any(
            c.get("fontname") != font
            or abs((c["top"] + c["bottom"]) / 2 - center) > height * 0.1
            or abs(c["bottom"] - c["top"] - height) > height * 0.05
            for c in blanks
        ):
            continue
        if any(
            b["x0"] <= a["x0"] or abs(b["x0"] - a["x1"]) > height * 0.25
            for a, b in zip(blanks, blanks[1:])
        ):
            continue
        left, right = first["x0"], blanks[-1]["x1"]
        later = []
        for c in chars[index : index + 256]:
            if (
                not eligible(c)
                or c.get("fontname") != font
                or abs((c["top"] + c["bottom"]) / 2 - center) > height * 0.1
                or not left <= (c["x0"] + c["x1"]) / 2 <= right
            ):
                break
            later.append(c)
        phrase = "".join(c["text"] for c in later).strip()
        if not re.fullmatch(r"[A-Za-z]+(?: +[A-Za-z]+){2,}", phrase):
            continue
        ink = [c for c in later if c["text"].strip()]
        covered = [
            c
            for c in blanks
            if any(
                g["x0"] < (c["x0"] + c["x1"]) / 2 < g["x1"]
                and min(g["bottom"], c["bottom"]) - max(g["top"], c["top"])
                >= height * 0.8
                for g in ink
            )
        ]
        if len(covered) >= max(6, len(ink) * 0.5):
            removed.update(id(c) for c in covered)
    return removed


def without_overprinted_blanks(page):
    if not hasattr(page, "filter") or not hasattr(page, "chars"):
        return page
    chars = page.chars
    visible = visible_glyphs(chars)
    if len(chars) == len(visible):
        return page
    keep = {id(ch) for ch in visible}
    return page.filter(lambda obj: obj.get("object_type") != "char" or id(obj) in keep)
