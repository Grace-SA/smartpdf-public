"""Restore verified source typography without changing cell text or spans."""

from collections import Counter, defaultdict
from itertools import accumulate
from statistics import median
import math
import unicodedata


def output_font_widths(cell):
    """Metrics for the workbook face, which can be wider than embedded PDF glyphs."""
    from pdfminer.fontmetrics import FONT_METRICS

    base = {
        "Arial": "Arial",
        "Times New Roman": "TimesNewRoman",
        "Courier New": "CourierNew",
    }.get(cell.get("fontName", "Arial"))
    if base is None:
        return {}
    style = ("Bold" if cell.get("bold") else "") + (
        "Italic" if cell.get("italic") else ""
    )
    key = base + ("," + style if style else "")
    return FONT_METRICS[key][1]


def valid_glyph(ch):
    vals = [ch.get(k, math.nan) for k in ("x0", "x1", "top", "bottom", "size", "width")]
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in vals):
        return False
    if (
        not ch.get("upright")
        or not 4 <= ch["size"] <= 72
        or not 0 < ch["width"] <= 512
        or ch["bottom"] <= ch["top"]
    ):
        return False
    a, b, c, d, _, _ = ch.get("matrix", (1, 0, 0, 1, 0, 0))
    return (
        a > 0
        and d > 0
        and abs(b) < 1e-6
        and abs(c) < 1e-6
        and abs(a - d) <= max(a, d) * 0.05
    )


def family(name):
    name = name.split("+")[-1].lower()
    if name.startswith(("timesnewroman", "times-")) or name == "times":
        return "Times New Roman"
    if name.startswith(("helvetica", "arial")):
        return "Arial"
    if name.startswith("courier"):
        return "Courier New"
    if name.startswith("calibri"):
        return "Calibri"
    return None


def apply_source_typography(table, page):
    if page.rotation or not table.get("bbox"):
        return 0
    box = table["bbox"]
    if not all(
        math.isfinite(v) for v in list(box) + table["widths"] + table["heights"]
    ) or any(v <= 0 for v in table["widths"] + table["heights"]):
        return 0
    if abs(sum(table["heights"]) - (box[3] - box[1])) > 3:
        return 0
    xs = list(accumulate(table["widths"], initial=table["bbox"][0]))
    ys = list(accumulate(table["heights"], initial=table["bbox"][1]))
    glyphs = [ch for ch in page.chars if valid_glyph(ch) and ch["text"].strip()]
    bands = defaultdict(list)
    for ch in glyphs:
        bands[math.floor((ch["top"] + ch["bottom"]) / 32)].append(ch)
    count = 0
    for cell in table["cells"]:
        if (
            cell.get("rotation")
            or not cell["text"].strip()
            or any(
                unicodedata.east_asian_width(ch) in ("W", "F") for ch in cell["text"]
            )
        ):
            continue
        r, c, rs, cs = [cell[k] for k in ["r", "c", "rs", "cs"]]
        nearby = [
            ch
            for band in bands
            if math.floor(ys[r] / 16) <= band <= math.floor(ys[r + rs] / 16)
            for ch in bands[band]
        ]
        chars = [
            ch
            for ch in nearby
            if xs[c] <= (ch["x0"] + ch["x1"]) / 2 < xs[c + cs]
            and ys[r] <= (ch["top"] + ch["bottom"]) / 2 < ys[r + rs]
        ]
        if not chars or Counter(
            ch for g in chars for ch in g["text"] if not ch.isspace()
        ) != Counter(ch for ch in cell["text"] if not ch.isspace()):
            chars = candidate_source(cell, bands, xs[c], xs[c + cs], ys[r], ys[r + rs])
            if not chars:
                chars = unique_source(
                    cell, nearby, xs[c], xs[c + cs], ys[r], ys[r + rs]
                )
            if not chars:
                continue
        names = {family(ch["fontname"]) for ch in chars}
        sizes = [ch["size"] for ch in chars]
        if (
            None in names
            or len(names) != 1
            or min(sizes) < 4
            or max(sizes) > 72
            or max(sizes) > min(sizes) * 1.05
        ):
            continue
        size = median(sizes)
        widths = defaultdict(list)
        for ch in chars:
            if len(ch["text"]) == 1:
                widths[ch["text"]].append(ch["width"])
        cell.update(
            fontName=names.pop(),
            fontSize=size,
            bold=all("bold" in ch["fontname"].lower() for ch in chars),
            italic=all(
                any(x in ch["fontname"].lower() for x in ["italic", "oblique"])
                for ch in chars
            ),
            sourceFont=True,
            glyphWidths={k: median(v) for k, v in widths.items()},
        )
        cell["sourceTextBox"] = [
            min(ch["x0"] for ch in chars),
            min(ch["top"] for ch in chars),
            max(ch["x1"] for ch in chars),
            max(ch["bottom"] for ch in chars),
        ]
        count += 1
    if count:
        table["sourceTypography"] = True
        refine_widths(table)
    return count


def candidate_source(cell, bands, x0, x1, y0, y1):
    """Use a model text box only when complete native glyphs verify it."""
    from pdfplumber.utils import extract_text

    b = cell.get("sourceTextCandidate")
    if (
        not isinstance(b, (list, tuple))
        or len(b) != 4
        or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in b)
    ):
        return []
    l, t, r, bottom = b
    if not (
        l < r and t < bottom and x0 <= (l + r) / 2 < x1 and y0 <= (t + bottom) / 2 < y1
    ):
        return []
    if (
        l < x0 - (x1 - x0) * 0.5
        or r > x1 + (x1 - x0) * 0.5
        or t < y0 - (y1 - y0) * 0.3
        or bottom > y1 + (y1 - y0) * 0.3
    ):
        return []
    glyphs = [
        ch
        for band in bands
        if math.floor((t - 4) / 16) <= band <= math.floor((bottom + 4) / 16)
        for ch in bands[band]
    ]
    expected = " ".join(cell["text"].split())
    nearby = [
        ch
        for ch in glyphs
        if l - 4 <= (ch["x0"] + ch["x1"]) / 2 <= r + 4
        and t - 4 <= (ch["top"] + ch["bottom"]) / 2 <= bottom + 4
    ]
    if not nearby:
        return []
    for padding in [0.5, min(4, median(ch["size"] for ch in nearby) * 0.5)]:
        chars = [
            ch
            for ch in nearby
            if l - padding <= (ch["x0"] + ch["x1"]) / 2 <= r + padding
            and t - padding <= (ch["top"] + ch["bottom"]) / 2 <= bottom + padding
        ]
        actual = (
            " ".join(extract_text(chars, x_tolerance=1.5, y_tolerance=2).split())
            if chars
            else ""
        )
        if actual == expected:
            return chars
    return []


def unique_source(cell, glyphs, x0, x1, y0, y1):
    from pdfplumber.utils import cluster_objects

    chars = [ch for ch in glyphs if y0 <= (ch["top"] + ch["bottom"]) / 2 < y1]
    if not chars:
        return []
    lines = cluster_objects(
        chars,
        lambda ch: (ch["top"] + ch["bottom"]) / 2,
        max(1, median(ch["size"] for ch in chars) * 0.2),
    )
    matches = [found for line in lines if (found := match_line(cell, line, x0, x1))]
    return matches[0] if len(matches) == 1 else []


def match_line(cell, chars, x0, x1):
    chars = sorted(chars, key=lambda ch: ch["x0"])
    target = "".join(cell["text"].split())
    flat = ""
    positions = []
    for ch in chars:
        text = "".join(ch["text"].split())
        flat += text
        positions.extend([ch] * len(text))
    start = flat.find(target)
    if start < 0 or flat.find(target, start + 1) >= 0:
        return []
    found = list({id(ch): ch for ch in positions[start : start + len(target)]}.values())
    a = min(ch["x0"] for ch in found)
    b = max(ch["x1"] for ch in found)
    if (
        not x0 <= (a + b) / 2 < x1
        or a < x0 - (x1 - x0) * 0.3
        or b > x1 + (x1 - x0) * 0.3
    ):
        return []
    # A partial word is not sufficient evidence for the cell's font.
    size = median(ch["size"] for ch in found)
    if start and a - positions[start - 1]["x1"] < size * 0.15:
        return []
    end = start + len(target)
    if end < len(positions) and positions[end]["x0"] - b < size * 0.15:
        return []
    return found


def refine_widths(table):
    if table.get("sourceGeometry"):
        return
    old = list(accumulate(table["widths"], initial=table["bbox"][0]))
    xs = list(old)
    for j in range(1, len(xs) - 1):
        left = [
            c["sourceTextBox"][2]
            for c in table["cells"]
            if c.get("sourceFont") and c["c"] + c["cs"] == j
        ]
        right = [
            c["sourceTextBox"][0]
            for c in table["cells"]
            if c.get("sourceFont") and c["c"] == j
        ]
        if len(left) < 3 or len(right) < 3:
            continue
        lo = max(left) + 1
        hi = min(right) - 1
        if lo > hi:
            continue
        value = (lo + hi) / 2
        if abs(value - old[j]) > min(old[j] - old[j - 1], old[j + 1] - old[j]) * 0.3:
            continue
        xs[j] = value
    if all(b - a >= 10 for a, b in zip(xs, xs[1:])):
        table["widths"] = [b - a for a, b in zip(xs, xs[1:])]


def readable_header_widths(table):
    widths = list(table["widths"])
    for c in table["cells"]:
        if (
            not c.get("sourceFont")
            or c.get("rotation")
            or c["r"] >= table.get("headerRows", 1)
            or c["cs"] != 1
        ):
            continue
        glyphs = c.get("glyphWidths", {})
        words = c["text"].split()
        if not words or any(ch not in glyphs for word in words for ch in word):
            continue
        desired = max(sum(glyphs[ch] for ch in word) for word in words) + 4
        col = c["c"]
        original = table["widths"][col]
        if original < desired <= original + max(8, original * 0.2):
            widths[col] = max(widths[col], desired)
    return widths
