"""Retain range spacing supported by both parser text and physical glyph gaps."""

import re
from statistics import median

_RANGE = re.compile(r"(\d[\d.,]*)(\s*)([-–—−])(\s*)(\d[\d.,]*)")


def restore_range_spaces(text, value, chars):
    old, new = _RANGE.fullmatch(text), _RANGE.fullmatch(value)
    if (
        not old
        or not new
        or not old[2]
        or not old[4]
        or (old[1], old[5]) != (new[1], new[5])
    ):
        return value
    chars = sorted((c for c in chars if c["text"].strip()), key=lambda c: c["x0"])
    dashes = [i for i, c in enumerate(chars) if c["text"] in "-–—−"]
    if len(dashes) != 1 or not 0 < dashes[0] < len(chars) - 1:
        return value
    i = dashes[0]
    threshold = max(0.5, median(c["width"] for c in chars) * 0.15)
    if (
        chars[i]["x0"] - chars[i - 1]["x1"] >= threshold
        and chars[i + 1]["x0"] - chars[i]["x1"] >= threshold
    ):
        return old[1] + old[2] + new[3] + old[4] + old[5]
    return value
