"""Recover source reading order inside a uniquely matched physical cell grid."""

from collections import Counter
from copy import deepcopy
import math
import unicodedata


def reading_order(value):
    """SpreadsheetML: explicit base direction for mixed RTL/LTR cell text."""
    if value.isascii():
        return 0
    directions = [unicodedata.bidirectional(ch) for ch in value]
    if not any(d in ("R", "AL") for d in directions) or any(
        d in ("LRE", "RLE", "LRO", "RLO", "PDF", "LRI", "RLI", "FSI", "PDI")
        for d in directions
    ):
        return 0
    first = next(d for d in directions if d in ("L", "R", "AL"))
    return 1 if first == "L" else 2


def has_rtl(value):
    if value.isascii():
        return False
    count = 0
    for char in value:
        count += unicodedata.bidirectional(char) in ("R", "AL")
        if count >= 2:
            return True
    return False


def reorder_value(value, source):
    # Exact whole tokens preserve numbers, signs, punctuation, case, combining
    # marks and repeated words. Only their reading order may change.
    if not has_rtl(value) or len(value.split()) < 2:
        return value
    if len([line for line in source.splitlines() if line.strip()]) != 1:
        return value
    if Counter(value.split()) != Counter(source.split()):
        return value
    return source.strip()


def signature(table):
    return {
        (c["r"], c["c"], c["rs"], c["cs"]): (
            Counter(
                ch
                for ch in unicodedata.normalize("NFKC", c["text"])
                if not ch.isspace()
            )
            if has_rtl(c["text"])
            else Counter(c["text"].split())
        )
        for c in table["cells"]
        if c["text"].strip()
    }


def recover(table, page, native_extractor):
    if getattr(page, "rotation", 0) or not any(
        has_rtl(c["text"]) for c in table["cells"]
    ):
        return table
    from layout_tables import overlap, visible_box

    bounds = table.get("bbox")
    if not bounds or not all(math.isfinite(v) for v in bounds):
        return table
    candidates = []
    for native in native_extractor(page):
        box = native.get("bbox")
        widths = native["widths"]
        heights = native["heights"]
        if (
            not native.get("closedGrid")
            or not box
            or len(widths) != len(table["widths"])
            or len(heights) != len(table["heights"])
            or not all(math.isfinite(v) and v > 0 for v in widths + heights)
            or overlap(bounds, box) < 0.9
            or abs(sum(widths) - (box[2] - box[0])) > 3
            or abs(sum(heights) - (box[3] - box[1])) > 3
            or signature(native) != signature(table)
        ):
            continue
        occupied = set()
        valid = True
        for c in native["cells"]:
            r, col, rs, cs = [c[k] for k in ["r", "c", "rs", "cs"]]
            if not all(isinstance(v, int) for v in [r, col, rs, cs]) or not (
                0 <= r < r + rs <= len(heights) and 0 <= col < col + cs <= len(widths)
            ):
                valid = False
                break
            region = {(y, x) for y in range(r, r + rs) for x in range(col, col + cs)}
            if region & occupied:
                valid = False
                break
            occupied.update(region)
        if valid and len(occupied) == len(widths) * len(heights):
            candidates.append(native)
    if len(candidates) != 1:
        return table
    native = candidates[0]
    xs = [native["bbox"][0]]
    ys = [native["bbox"][1]]
    for width in native["widths"]:
        xs.append(xs[-1] + width)
    for height in native["heights"]:
        ys.append(ys[-1] + height)
    root = getattr(page, "root_page", page)
    stream = page.pdf.stream
    position = stream.tell()
    try:
        stream.seek(0)
        payload = stream.read()
    finally:
        stream.seek(position)
    replacements = {}
    view = visible_box(page)
    originals = {(c["r"], c["c"]): c["text"] for c in table["cells"]}
    try:
        import pypdfium2 as pdfium

        with pdfium.PdfDocument(payload) as document:
            source_page = document[page.page_number - 1]
            text_page = source_page.get_textpage()
            try:
                for c in native["cells"]:
                    original = originals.get((c["r"], c["c"]), "")
                    if not has_rtl(original) or len(original.split()) < 2:
                        continue
                    l, r = xs[c["c"]], xs[c["c"] + c["cs"]]
                    top, bottom = ys[c["r"]], ys[c["r"] + c["rs"]]
                    if not (
                        view[0] <= l < r <= view[2]
                        and view[1] <= top < bottom <= view[3]
                    ):
                        continue
                    source = text_page.get_text_bounded(
                        l, root.height - bottom, r, root.height - top
                    )
                    value = reorder_value(original, source)
                    if value != original:
                        replacements[c["r"], c["c"]] = value
            finally:
                text_page.close()
                source_page.close()
    except (ImportError, ValueError, RuntimeError, OSError):
        return table
    if not replacements:
        return table
    result = deepcopy(table)
    for c in result["cells"]:
        if (c["r"], c["c"]) in replacements:
            c["text"] = replacements[c["r"], c["c"]]
    return result
