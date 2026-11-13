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


def horizontal(chars):
    if len(chars) < 10:
        return False
    for char in chars:
        matrix = char.get("matrix")
        if not matrix or len(matrix) != 6:
            return False
        a, b, c, d, _, _ = matrix
        if not all(math.isfinite(v) for v in matrix):
            return False
        scale = max(abs(a), abs(d), 1e-9)
        if a <= 0 or d <= 0 or abs(b) > scale * 0.001 or abs(c) > scale * 0.001:
            return False
    return True


@contextmanager
def prepared_rotation(source, selected, output_directory):
    """Remove /Rotate only when all visible native glyphs become horizontal.

    No OCR, arbitrary deskew or text reconstruction is performed. Retain the
    original media/crop boxes and require identical complete glyph multisets. The unchanged PDF crop box
    selects the same source region before and after changing display orientation.
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
        accepted = []
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
                new_chars = visible_chars(after)
                if (
                    not before.images
                    and not after.images
                    and horizontal(new_chars)
                    and Counter(c["text"] for c in before.chars)
                    == Counter(c["text"] for c in after.chars)
                ):
                    accepted.append(i)
        if not accepted:
            yield source, []
            return
        for i in candidates:
            if i not in accepted:
                writer.pages[i].rotation = reader.pages[i].rotation
        target = Path(tmp) / "normalized.pdf"
        writer.write(target)
        yield target, [i + 1 for i in accepted]
