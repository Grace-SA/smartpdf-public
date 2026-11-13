"""Recover complete native word sequences clipped by a model text box."""

import math
from statistics import median
import unicodedata


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
