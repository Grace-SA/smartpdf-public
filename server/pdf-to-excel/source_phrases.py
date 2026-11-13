"""Recover complete native word sequences clipped by a model text box."""

import math
from statistics import median
import unicodedata


def restore_line_order(text, original, chars):
    """Recover visual line order only for an exact permutation of complete lines."""
    from itertools import permutations

    lines = [line.strip() for line in original.splitlines() if line.strip()]
    if not 2 <= len(lines) <= 4 or not any(ch.isalpha() for ch in original):
        return None
    keys = [canonical(line) for line in lines]
    if len(set(keys)) != len(keys) or any(not key for key in keys):
        return None
    sizes = [ch.get("size") for ch in chars if ch["text"].strip()]
    if (
        not sizes
        or any(
            not isinstance(s, (int, float)) or not math.isfinite(s) or s <= 0
            for s in sizes
        )
        or max(sizes) > min(sizes) * 1.2
    ):
        return None
    # A clipped model box can contain text from adjacent columns. Disjoint
    # horizontal extents are not evidence of a multi-line phrase.
    from pdfplumber.utils import cluster_objects

    ink = [ch for ch in chars if ch["text"].strip()]
    if any(
        not isinstance(ch.get(k), (int, float)) or not math.isfinite(ch[k])
        for ch in ink
        for k in ["x0", "x1", "top", "bottom"]
    ):
        return None
    groups = cluster_objects(ink, lambda ch: ch["top"], 3)
    if len(groups) != len(lines):
        return None
    spans = [
        (min(ch["x0"] for ch in group), max(ch["x1"] for ch in group))
        for group in groups
    ]
    if max(left for left, right in spans) >= min(right for left, right in spans):
        return None
    wanted = canonical(text)
    if wanted == "".join(keys):
        return None
    matching = [
        order
        for order in permutations(range(len(lines)))
        if "".join(keys[i] for i in order) == wanted
    ]
    if len(matching) != 1:
        return None
    return ("\n" if "\n" in text else " ").join(lines)


def canonical(text):
    return "".join(
        unicodedata.normalize("NFKC", text)
        .translate(
            str.maketrans(
                {
                    "–": "-",
                    "—": "-",
                    "−": "-",
                    "‐": "-",
                    "‑": "-",
                    "‘": "'",
                    "’": "'",
                    "“": '"',
                    "”": '"',
                    "•": "·",
                }
            )
        )
        .split()
    ).casefold()


def recover(text, box, page, view):
    if (
        not hasattr(page, "extract_words")
        or not text.strip()
        or not all(math.isfinite(v) for v in box)
    ):
        return text
    words = getattr(page, "_excel_phrase_words", None)
    if words is None:
        words = [
            w
            for w in page.extract_words(x_tolerance=2, y_tolerance=3, return_chars=True)
            if w.get("upright")
            and all(math.isfinite(w[k]) for k in ["x0", "x1", "top", "bottom"])
            and view[0] <= w["x0"] < w["x1"] <= view[2]
            and view[1] <= w["top"] < w["bottom"] <= view[3]
        ]
        page._excel_phrase_words = words
    selected = [
        w
        for w in words
        if box[0] - 0.5 <= (w["x0"] + w["x1"]) / 2 <= box[2] + 0.5
        and box[1] - 0.5 <= (w["top"] + w["bottom"]) / 2 <= box[3] + 0.5
    ]
    if not 2 <= len(selected) <= 20:
        return text
    heights = [w["bottom"] - w["top"] for w in selected]
    height = median(heights)
    if not 3 <= height <= 40 or max(
        (w["top"] + w["bottom"]) / 2 for w in selected
    ) - min((w["top"] + w["bottom"]) / 2 for w in selected) > min(2.5, height * 0.25):
        return text
    selected.sort(key=lambda w: w["x0"])
    if any(
        b["x0"] - a["x1"] > height * 0.65 or b["x0"] < a["x1"] - 0.2
        for a, b in zip(selected, selected[1:])
    ):
        return text
    # At most one font-height may overhang either clipped end. All whole word
    # centers, and every other word inside the box, must agree on literal content.
    if selected[0]["x0"] < box[0] - height or selected[-1]["x1"] > box[2] + height:
        return text
    # A superscript marker can be joined to its preceding word by the native
    # word extractor. This fallback cannot safely reassign those boundaries.
    sizes = [
        ch["size"]
        for word in selected
        for ch in word.get("chars", [])
        if ch["text"].strip()
        and isinstance(ch.get("size"), (int, float))
        and math.isfinite(ch["size"])
        and ch["size"] > 0
    ]
    if sizes and max(sizes) > min(sizes) * 1.2:
        return text
    original = " ".join(w["text"] for w in selected)
    if canonical(original) != canonical(text):
        return text
    from layout_ranges import restore_range_spaces

    chars = [ch for word in selected for ch in word.get("chars", [])]
    return restore_range_spaces(text, original, chars)
