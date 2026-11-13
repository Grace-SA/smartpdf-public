"""Preserve bounded native page context without inventing footnote associations."""

import math

from layout_tables import visible_box
from source_rotation import quarter_turn


def page_context(page, tables):
    """Return text fully outside every detected table and inside the visible page.

    Unknown table boundaries and mixed-direction context are intentionally not
    guessed. Context is page-level evidence, not a reconstructed reading order.
    """
    boxes = [table.get("bbox") for table in tables]
    if not boxes or any(
        not box
        or len(box) != 4
        or not all(math.isfinite(v) for v in box)
        or box[0] >= box[2]
        or box[1] >= box[3]
        for box in boxes
    ):
        return ""
    left, top, right, bottom = visible_box(page)

    def outside(char):
        return (
            char.get("object_type") == "char"
            and left <= char["x0"] <= char["x1"] <= right
            and top <= char["top"] <= char["bottom"] <= bottom
            and all(
                char["x1"] < box[0]
                or char["x0"] > box[2]
                or char["bottom"] < box[1]
                or char["top"] > box[3]
                for box in boxes
            )
        )

    filtered = page.filter(outside)
    chars = [c for c in filtered.chars if c.get("text", "").strip()]
    # quarter_turn deliberately requires ten glyphs. Short notes are checked
    # using repeated references, not fabricated or repeated output text.
    if (
        not chars
        or len(chars) > 16000
        or quarter_turn(chars * (10 // len(chars) + 1)) != 0
    ):
        return ""
    text = filtered.extract_text(x_tolerance=2, y_tolerance=3) or ""
    if len(text) > 16000 or any(
        not (
            c in "\n\t\r"
            or 0x20 <= ord(c) <= 0xD7FF
            or 0xE000 <= ord(c) <= 0xFFFD
            or 0x10000 <= ord(c) <= 0x10FFFF
        )
        for c in text
    ):
        return ""
    return text.strip()
