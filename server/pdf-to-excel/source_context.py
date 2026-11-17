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
    return valid_context(text)


def valid_context(text):
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


def ocr_page_context(lines, table_boxes, image_size):
    # Optional evidence must not make otherwise usable table output fail when
    # an OCR provider returns a malformed result. Do not salvage partial notes.
    try:
        return _ocr_page_context(lines, table_boxes, image_size)
    except (TypeError, ValueError, OverflowError, IndexError):
        return ""


def _ocr_page_context(lines, table_boxes, image_size):
    """Preserve high-confidence raster context; never correct recognized text.

    Coordinates are in the same raster pixels as table boxes. Table-overlapping
    regions are excluded. Arbitrary-angle text and uncertain context invalidate
    the context, not the table. Returned text is explicitly labelled OCR by the workbook writer.
    """
    width, height = image_size
    if not table_boxes or not (0 < width <= 200000 and 0 < height <= 200000):
        return ""
    if any(
        len(b) != 4
        or not all(math.isfinite(v) for v in b)
        or not (0 <= b[0] < b[2] <= width and 0 <= b[1] < b[3] <= height)
        for b in table_boxes
    ):
        return ""
    context = []
    length = 0
    for box, text, score in lines:
        if not isinstance(text, str):
            return ""
        if len(box) != 4 or any(
            len(p) != 2 or not all(math.isfinite(v) for v in p) for p in box
        ):
            return ""
        left, right = min(p[0] for p in box), max(p[0] for p in box)
        top, bottom = min(p[1] for p in box), max(p[1] for p in box)
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            continue
        if any(
            not (right < b[0] or left > b[2] or bottom < b[1] or top > b[3])
            for b in table_boxes
        ):
            continue
        if not text.strip():
            continue
        # Long horizontal lines can acquire a few pixels of detector jitter.
        # Bound it by both baseline length (about 1.15 degrees) and line height;
        # never infer rotation or alter the recognized text.
        top_tolerance = max(
            3, min((box[1][0] - box[0][0]) * 0.02, (bottom - top) * 0.15)
        )
        bottom_tolerance = max(
            3, min((box[2][0] - box[3][0]) * 0.02, (bottom - top) * 0.15)
        )
        # RapidOCR polygons are TL, TR, BR, BL. Do not reorder vertical or
        # skewed annotations based only on their axis-aligned bounding boxes.
        if (
            not math.isfinite(float(score))
            or not 0.85 <= float(score) <= 1
            or box[1][0] <= box[0][0]
            or box[2][0] <= box[3][0]
            or abs(box[0][1] - box[1][1]) > top_tolerance
            or abs(box[2][1] - box[3][1]) > bottom_tolerance
        ):
            return ""
        context.append((top, left, text))
        length += len(text) + 1
        if length > 16000:
            return ""
    context.sort(key=lambda item: (item[0], item[1]))
    return valid_context("\n".join(item[2] for item in context))
