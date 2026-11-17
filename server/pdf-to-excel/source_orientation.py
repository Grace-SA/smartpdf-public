"""Identify a predominantly sideways native text page without guessing from labels."""

import math
from collections import Counter
from contextlib import contextmanager
from tempfile import TemporaryDirectory
from pathlib import Path
import pdfplumber
from pypdf import PdfReader, PdfWriter


def sideways_turn(page):
    from layout_tables import visible_box

    view = visible_box(page)
    counts = Counter()
    for char in page.chars:
        text = char["text"]
        if not any(ch.isalnum() for ch in text):
            continue
        if not (
            view[0] <= char["x0"] <= char["x1"] <= view[2]
            and view[1] <= char["top"] <= char["bottom"] <= view[3]
        ):
            continue
        matrix = char.get("matrix")
        if (
            not matrix
            or len(matrix) != 6
            or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in matrix)
        ):
            counts["other"] += 1
            continue
        a, b, c, d = matrix[:4]
        scale = max(abs(b), abs(c))
        if scale > 0 and max(abs(a), abs(d)) <= scale * 0.01 and b * c < 0:
            counts[90 if b > 0 else 270] += 1
        else:
            counts["other"] += 1
    total = sum(counts.values())
    return (
        max((90, 270), key=lambda angle: counts[angle])
        if total >= 50 and max(counts[90], counts[270]) >= total * 0.95
        else None
    )


def sideways_text(page):
    return sideways_turn(page) is not None


@contextmanager
def upright_source(source, selected, output_directory):
    """Normalize demonstrably sideways native text in a temporary PDF copy."""
    turns = {}
    with pdfplumber.open(source) as doc:
        for index in selected:
            turn = sideways_turn(doc.pages[index])
            if turn is not None:
                turns[index] = turn
    if not turns:
        yield source, []
        return
    with TemporaryDirectory(
        prefix=".pdf-excel-upright-", dir=output_directory
    ) as folder:
        writer = PdfWriter(clone_from=PdfReader(source))
        for index, turn in turns.items():
            page = writer.pages[index]
            page.rotate(turn)
            page.transfer_rotation_to_content()
        output = Path(folder) / "input.pdf"
        writer.write(output)
        yield output, [index + 1 for index in turns]
