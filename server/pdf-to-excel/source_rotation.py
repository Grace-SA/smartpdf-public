"""Normalize sideways native text in a temporary copy, never the source PDF."""

import math
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

import pdfplumber
from layout_tables import visible_box
from pypdf import PdfReader, PdfWriter


def visible_chars(page):
    left, top, right, bottom = visible_box(page)
    return [
        c
        for c in page.chars
        if c.get("text", "").strip()
        and left <= (c["x0"] + c["x1"]) / 2 <= right
        and top <= (c["top"] + c["bottom"]) / 2 <= bottom
    ]


def quarter_turn(chars):
    """Find one exact common native baseline orientation, never majority-vote."""
    if len(chars) < 10:
        return None
    directions = {glyph_direction(char) for char in chars}
    return directions.pop() if len(directions) == 1 and None not in directions else None


def glyph_direction(char):
    matrix = char.get("matrix")
    if not matrix or len(matrix) != 6 or not all(
        isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
        for v in matrix
    ):
        return None
    a, b, c, d, _, _ = matrix
    tolerance = max(abs(a), abs(b), abs(c), abs(d), 1e-9) * 0.001
    if abs(b) <= tolerance and abs(c) <= tolerance:
        return 0 if a > 0 and d > 0 else 180 if a < 0 and d < 0 else None
    if abs(a) <= tolerance and abs(d) <= tolerance:
        return 90 if b > 0 and c < 0 else 270 if b < 0 and c > 0 else None
    return None


def unresolved_dominant_turn(chars):
    """Refuse, never rotate, strongly sideways native text with mixed directions.

    A short upright page number must not allow an otherwise sideways table into
    horizontal reconstruction. This narrow refusal leaves ordinary horizontal
    bodies with some vertical headings unchanged; it is not a general orientation
    detector or a claim that below-threshold pages are correct.
    """
    if len(chars) < 20:
        return False
    counts = Counter(glyph_direction(char) for char in chars)
    return any(counts[angle] * 10 >= len(chars) * 9 for angle in (90, 180, 270))


def horizontal(chars):
    return quarter_turn(chars) == 0


@contextmanager
def prepared_rotation(source, selected, output_directory):
    """Orient pages only when all visible native glyphs share a quarter-turn.

    No OCR, arbitrary deskew or text reconstruction is performed. Retain the
    source view by rotating its media/crop boxes together with its contents.
    Require identical complete glyph multisets and horizontal output baselines.
    Mixed/image pages and pages with differently oriented text stay unchanged.
    """
    reader = PdfReader(source)
    candidates = [i for i in selected if reader.pages[i].rotation in (90, 180, 270)]
    if not candidates:
        yield source, []
        return
    with TemporaryDirectory(prefix=".pdf-excel-rotation-", dir=output_directory) as tmp:
        trial = Path(tmp) / "trial.pdf"
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        for i in candidates:
            writer.pages[i].rotation = 0
        writer.write(trial)
        accepted = {}
        with pdfplumber.open(source) as original, pdfplumber.open(trial) as normalized:
            for i in candidates:
                before, after = original.pages[i], normalized.pages[i]
                boxes = [visible_box(before), visible_box(after)]
                if any(
                    not all(math.isfinite(v) for v in box)
                    or box[2] <= box[0]
                    or box[3] <= box[1]
                    or (box[2] - box[0]) * (box[3] - box[1]) > 10_000_000
                    for box in boxes
                ):
                    # The conversion entry point rejects this page with its
                    # normal dimension error; do not parse its content first.
                    continue
                direction = quarter_turn(visible_chars(after))
                if (
                    not before.images
                    and not after.images
                    and direction is not None
                    and Counter(c["text"] for c in before.chars)
                    == Counter(c["text"] for c in after.chars)
                ):
                    accepted[i] = direction
        if not accepted:
            yield source, []
            return
        for i in candidates:
            if i not in accepted:
                writer.pages[i].rotation = reader.pages[i].rotation
            elif accepted[i]:
                writer.pages[i].rotation = accepted[i]
                writer.pages[i].transfer_rotation_to_content()
        target = Path(tmp) / "normalized.pdf"
        writer.write(target)
        with pdfplumber.open(source) as original, pdfplumber.open(target) as normalized:
            for i in accepted:
                if not horizontal(visible_chars(normalized.pages[i])) or Counter(
                    c["text"] for c in original.pages[i].chars
                ) != Counter(c["text"] for c in normalized.pages[i].chars):
                    yield source, []
                    return
        yield target, [i + 1 for i in accepted]
