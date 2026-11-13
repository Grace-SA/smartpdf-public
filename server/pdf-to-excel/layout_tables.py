"""Offline layout/structure adapter; models never generate cell text."""

from collections import Counter, defaultdict
import math
from statistics import median
from functools import lru_cache
import io
import os
import re
import unicodedata
from pathlib import Path
from source_glyphs import visible_glyphs, without_overprinted_blanks


class LayoutError(Exception):
    pass


def top_box(box, height):
    if box.get("coord_origin") == "BOTTOMLEFT":
        return [box["l"], height - box["t"], box["r"], height - box["b"]]
    return [box["l"], box["t"], box["r"], box["b"]]


def visible_box(page):
    """PDF object coordinates can have non-zero origins and hidden margins."""
    media = getattr(page, "bbox", (0, 0, getattr(page, "width", math.inf), page.height))
    crop = getattr(page, "cropbox", None) or media
    return [
        max(media[0], crop[0]),
        max(media[1], crop[1]),
        min(media[2], crop[2]),
        min(media[3], crop[3]),
    ]


def physical_page(page):
    """Exclude background fills from rules, retaining stroked boxes and thin bars.

    Some PDF writers paint a cell background as several adjoining rectangles.
    Their invisible boundaries are not cell separators. Thin filled rectangles
    remain because many writers draw actual grid lines with those primitives.
    """
    if not hasattr(page, "filter"):
        return page
    cached = getattr(page, "_excel_physical_page", None)
    if cached is not None:
        return cached
    original = page
    page = without_overprinted_blanks(page)
    result = page.filter(
        lambda obj: not (
            obj.get("object_type") == "rect"
            and not obj.get("stroke")
            and obj.get("fill")
            and obj.get("width", 0) > 3
            and obj.get("height", 0) > 3
        )
    )
    # A loaded PDF page is immutable throughout conversion. Keep this cache on
    # that page only; cropped/rotated pages are distinct page objects.
    original._excel_physical_page = result
    result._excel_physical_page = result
    return result


def model_box(box, page):
    view = visible_box(page)
    local = top_box(box, view[3] - view[1])
    return [
        local[0] + view[0],
        local[1] + view[1],
        local[2] + view[0],
        local[3] + view[1],
    ]


def local_box(box, page):
    view = visible_box(page)
    return dict(
        l=box[0] - view[0],
        t=box[1] - view[1],
        r=box[2] - view[0],
        b=box[3] - view[1],
        coord_origin="TOPLEFT",
    )


def overlap(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0, min(a[3], b[3]) - max(a[1], b[1])
    )
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / union if union > 0 else 0


def source_cell_text(text, box, page):
    """Restore original glyphs only when a second extractor agrees on content.

    Docling's parser normalizes dashes/quotes and can change case. Canonical
    comparison is an admission check only; the workbook receives PDF glyphs,
    never the canonicalized string. Numeric or word differences are not guessed.
    """
    if not hasattr(page, "chars") or not box:
        return text
    from pdfplumber.utils import extract_text

    b = model_box(box, page)
    view = visible_box(page)
    if not all(math.isfinite(v) for v in b) or b[3] < b[1]:
        return text
    bands = getattr(page, "_excel_glyph_bands", None)
    if bands is None:
        bands = defaultdict(list)
        for char in visible_glyphs(page.chars):
            bands[math.floor((char["top"] + char["bottom"]) / 32)].append(char)
        page._excel_glyph_bands = bands
    chars = [
        c
        for band in bands
        if math.floor((b[1] - 0.5) / 16) <= band <= math.floor((b[3] + 0.5) / 16)
        for c in bands[band]
        if b[0] - 0.5 <= (c["x0"] + c["x1"]) / 2 <= b[2] + 0.5
        and b[1] - 0.5 <= (c["top"] + c["bottom"]) / 2 <= b[3] + 0.5
        and view[0] <= (c["x0"] + c["x1"]) / 2 <= view[2]
        and view[1] <= (c["top"] + c["bottom"]) / 2 <= view[3]
    ]
    original = extract_text(chars, x_tolerance=2, y_tolerance=3) if chars else ""

    def canonical(value):
        value = unicodedata.normalize("NFKC", value)
        value = value.translate(
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
        return "".join(value.split()).casefold()

    if original and canonical(text) != canonical(original):
        # Predicted text boxes can overlap a neighbouring header line. Recover
        # glyphs from a unique sequence of complete source lines only; never
        # match a substring of an amount or discard another value on that line.
        lines = original.splitlines()
        keys = [canonical(line) for line in lines]
        joined = "".join(keys)
        wanted = canonical(text)
        start = joined.find(wanted) if wanted else -1
        if start >= 0 and joined.find(wanted, start + 1) < 0:
            offsets = [0]
            for key in keys:
                offsets.append(offsets[-1] + len(key))
            end = start + len(wanted)
            if start in offsets and end in offsets:
                original = "\n".join(lines[offsets.index(start) : offsets.index(end)])
    if original and canonical(text) == canonical(original):
        # A PDF's visual soft wraps must not become extra hard Excel breaks;
        # combining those with Excel wrapping can double the required row height.
        from layout_ranges import restore_range_spaces

        value = original if "\n" in text else original.replace("\n", " ")
        return restore_range_spaces(text, value, chars)
    # Some predicted boxes clip the first/last glyph of one complete word.
    # Recover that word only with exact canonical content and a unique centre
    # inside the prediction. Never recover words crossing the visible crop.
    if text.strip() and hasattr(page, "extract_words"):
        words = getattr(page, "_excel_source_words", None)
        if words is None:
            words = defaultdict(list)
            for word in page.extract_words(x_tolerance=2, y_tolerance=3):
                if (
                    view[0] <= word["x0"] <= word["x1"] <= view[2]
                    and view[1] <= word["top"] <= word["bottom"] <= view[3]
                ):
                    words[canonical(word["text"])].append(word)
            page._excel_source_words = words
        candidates = [
            word
            for word in words.get(canonical(text), [])
            if b[0] - 1 <= (word["x0"] + word["x1"]) / 2 <= b[2] + 1
            and b[1] - 1 <= (word["top"] + word["bottom"]) / 2 <= b[3] + 1
        ]
        if len(candidates) == 1:
            return candidates[0]["text"]
    from source_phrases import recover as recover_phrase

    return recover_phrase(text, b, page, view)


def adapt_table(item, page):
    data = item["data"]
    rows, columns = data["num_rows"], data["num_cols"]
    if not rows or not columns or rows * columns > 250000:
        raise LayoutError("The detected table exceeds the cell budget.")
    box = model_box(item["prov"][0]["bbox"], page)
    if not all(math.isfinite(v) for v in box) or box[2] <= box[0] or box[3] <= box[1]:
        raise LayoutError("The detected table has invalid dimensions.")
    occupied = set()
    cells = []
    x_centers, y_centers = defaultdict(list), defaultdict(list)
    for cell in data["table_cells"]:
        r, c = cell["start_row_offset_idx"], cell["start_col_offset_idx"]
        rs, cs = cell.get("row_span", 1), cell.get("col_span", 1)
        if r < 0 or c < 0 or rs < 1 or cs < 1 or r + rs > rows or c + cs > columns:
            raise LayoutError("The detected table has inconsistent cell coordinates.")
        region = {(y, x) for y in range(r, r + rs) for x in range(c, c + cs)}
        if region & occupied:
            raise LayoutError("The detected table has overlapping cells.")
        occupied.update(region)
        cells.append(
            {
                "r": r,
                "c": c,
                "rs": rs,
                "cs": cs,
                "text": source_cell_text(cell["text"], cell.get("bbox"), page),
                "sourceTextCandidate": (
                    model_box(cell["bbox"], page) if cell.get("bbox") else None
                ),
            }
        )
        if cell.get("bbox") and cell["text"].strip():
            cb = model_box(cell["bbox"], page)
            if cs == 1:
                x_centers[c].append((cb[0] + cb[2]) / 2)
            if rs == 1:
                y_centers[r].append((cb[1] + cb[3]) / 2)
    if not any(cell["text"].strip() for cell in cells):
        raise LayoutError(
            "A detected table has no readable text. Try a clearer scan or OCR."
        )

    def sizes(start, end, count, centers):
        anchors = [
            (
                median(centers[i])
                if centers[i]
                else start + (i + 0.5) * (end - start) / count
            )
            for i in range(count)
        ]
        boundaries = (
            [start] + [(a + b) / 2 for a, b in zip(anchors, anchors[1:])] + [end]
        )
        if any(b <= a for a, b in zip(boundaries, boundaries[1:])):
            return [(end - start) / count] * count
        return [b - a for a, b in zip(boundaries, boundaries[1:])]

    return {
        "widths": sizes(box[0], box[2], columns, x_centers),
        "heights": sizes(box[1], box[3], rows, y_centers),
        "cells": cells,
        "bbox": box,
        "method": "layout",
    }


def restore_rotated_headers(model, native):
    """Restore uniquely matched clipped headers and source currency literals."""
    from copy import deepcopy

    def canonical(value):
        return "".join(value.split())

    def digits(value):
        return re.findall(r"\d[\d.,]*", canonical(value))

    options = []
    for candidate in native:
        if len(candidate["heights"]) != len(model["heights"]) or len(
            candidate["widths"]
        ) != len(model["widths"]):
            continue
        source = {(c["r"], c["c"]): c for c in candidate["cells"] if c["text"].strip()}
        old = {(c["r"], c["c"]): c for c in model["cells"] if c["text"].strip()}
        if source.keys() != old.keys():
            continue
        changes = {}
        valid = True
        for key, cell in old.items():
            other = source[key]
            if (cell["rs"], cell["cs"]) != (other["rs"], other["cs"]):
                valid = False
                break
            before, after = canonical(cell["text"]), canonical(other["text"])
            if before == after:
                continue
            # Spreadsheet parsers can drop the currency format while retaining
            # its numeric string. Only add one literal source currency symbol;
            # decimal places, sign, separators and leading zeros must agree.
            currency = re.fullmatch(r"([$€£¥])([+\-−]?\d[\d.,]*)", after)
            if currency and currency.group(2) == before and candidate.get("closedGrid"):
                changes[key] = other["text"]
                continue
            if (
                cell["r"] != 0
                or not any(c.isalpha() for c in before)
                or before not in after
                or digits(before) != digits(after)
            ):
                valid = False
                break
            changes[key] = other["text"]
        if valid and changes:
            options.append(changes)
    if len(options) != 1:
        return model
    cells = deepcopy(model["cells"])
    for c in cells:
        if (c["r"], c["c"]) in options[0]:
            c["text"] = options[0][c["r"], c["c"]]
    return dict(model, cells=cells)


def prefer_native(model, native):
    """Use exact ruled geometry only when independent structure agrees in size."""

    def texts(table):
        return Counter(
            "".join(c["text"].split()) for c in table["cells"] if c["text"].strip()
        )

    def preserves_values(candidate):
        before = texts(model)
        after = texts(candidate)
        if before == after:
            return True
        # A complete physical grid can recover clipped headings. Every old
        # cell must still occur in its own corresponding cell, and numerical
        # tokens must be identical: extra prose cannot hide a changed amount.
        indexed = {(c["r"], c["c"]): c for c in candidate["cells"]}
        for cell in model["cells"]:
            if not cell["text"].strip():
                continue
            other = indexed.get((cell["r"], cell["c"]))
            if not other or (cell["rs"], cell["cs"]) != (other["rs"], other["cs"]):
                return False
            old = "".join(cell["text"].split())
            new = "".join(other["text"].split())
            if old not in new:
                return False
            if re.findall(r"\d[\d.,]*", old) != re.findall(r"\d[\d.,]*", new):
                return False
        return True

    for candidate in native:
        if (
            overlap(candidate["bbox"], model["bbox"]) >= 0.7
            and len(candidate["widths"]) == len(model["widths"])
            and len(candidate["heights"]) == len(model["heights"])
        ):
            if preserves_values(candidate):
                return candidate
            restored = restore_native_spans(model, candidate)
            if restored is not model:
                return restored
    return model


def restore_native_spans(model, physical):
    """Recover physically bounded label spans without collapsing data rows.

    A complete matching grid can establish that a wrapped label occupies one
    cell. Multiple numeric values, independently capitalized labels and existing
    model spans are not joined. A single label may expand into verified empty
    cells; short CJK fragments can join inside one physical vertical cell.
    """
    from copy import deepcopy

    if not physical.get("closedGrid"):
        return model
    # Extending an existing span or joining CJK fragments requires more than
    # one proposed rectangle: verify the complete grid and all numeric anchors.
    pr, pc = len(physical.get("heights", [])), len(physical.get("widths", []))
    verified_grid = (
        pr > 1
        and pc > 1
        and pr == len(model.get("heights", []))
        and pc == len(model.get("widths", []))
    )
    covered = set()
    physical_index = {(c["r"], c["c"]): c for c in physical["cells"]}
    if verified_grid:
        for entry in physical["cells"]:
            r, c, rs, cs = (entry[k] for k in ("r", "c", "rs", "cs"))
            if not 0 <= r < r + rs <= pr or not 0 <= c < c + cs <= pc:
                verified_grid = False
                break
            area = {(y, x) for y in range(r, r + rs) for x in range(c, c + cs)}
            if covered & area:
                verified_grid = False
                break
            covered.update(area)
        verified_grid = verified_grid and len(covered) == pr * pc
    if verified_grid:
        for entry in model["cells"]:
            if not any(ch.isdigit() for ch in entry["text"]):
                continue
            other = physical_index.get((entry["r"], entry["c"]))
            if (
                other is None
                or (entry["rs"], entry["cs"]) != (other["rs"], other["cs"])
                or "".join(entry["text"].split()) != "".join(other["text"].split())
            ):
                verified_grid = False
                break
    cells = deepcopy(model["cells"])
    changed = False
    for target in physical["cells"]:
        if target["rs"] == 1 and target["cs"] == 1:
            continue
        start, end = target["r"], target["r"] + target["rs"]
        left, right = target["c"], target["c"] + target["cs"]
        members = [
            c
            for c in cells
            if c["r"] < end
            and c["r"] + c["rs"] > start
            and c["c"] < right
            and c["c"] + c["cs"] > left
        ]
        if not members or any(
            c["r"] < start
            or c["r"] + c["rs"] > end
            or c["c"] < left
            or c["c"] + c["cs"] > right
            for c in members
        ):
            continue
        nonempty = sorted(
            [c for c in members if c["text"].strip()], key=lambda c: (c["r"], c["c"])
        )
        if len(members) == 1 and all(
            members[0][key] == target[key] for key in ("r", "c", "rs", "cs")
        ):
            # An already correct span retains its text and typography evidence.
            continue
        existing_span = any(c["rs"] > 1 or c["cs"] > 1 for c in members)
        if existing_span and not (
            verified_grid
            and len(nonempty) == 1
            and target["cs"] == nonempty[0]["cs"] == 1
            and target["r"] == nonempty[0]["r"]
            and target["c"] == nonempty[0]["c"]
            and any(ch.isalpha() for ch in nonempty[0]["text"])
            and not any(ch.isdigit() for ch in nonempty[0]["text"])
        ):
            continue
        cjk_fragments = verified_grid and all(
            1 <= len("".join(c["text"].split())) <= 8
            and all("\u3400" <= ch <= "\u9fff" for ch in c["text"] if not ch.isspace())
            for c in nonempty
        )
        if len(nonempty) > 1 and (
            target["cs"] != 1
            or target["rs"] > 4
            or any(any(ch.isdigit() for ch in c["text"]) for c in nonempty)
            or (
                not cjk_fragments
                and any(not c["text"].lstrip()[0].islower() for c in nonempty[1:])
            )
        ):
            continue
        before = "".join("".join(c["text"].split()) for c in nonempty)
        if not before or before != "".join(target["text"].split()):
            continue
        cells = [c for c in cells if c not in members] + [dict(target)]
        changed = True
    return dict(model, cells=cells) if changed else model


def recover_ruled_prediction(item, page, native):
    """Use a complete physical grid only when all predicted characters survive.

    This route is limited to conflicting model spans. Digit counts must agree
    exactly; source-extracted extra prose is limited to 5%. It cannot recover a
    corrupt PDF, an oversized table or an invalid model coordinate budget.
    """
    before = Counter("".join(c["text"] for c in item["data"]["table_cells"]))
    before = Counter({k: v for k, v in before.items() if not k.isspace()})
    box = model_box(item["prov"][0]["bbox"], page)
    for table in native:
        if not table.get("closedGrid") or overlap(box, table["bbox"]) < 0.85:
            continue
        after = Counter("".join(c["text"] for c in table["cells"]))
        after = Counter({k: v for k, v in after.items() if not k.isspace()})
        if (
            not before
            or before - after
            or sum(after.values()) > sum(before.values()) * 1.05
        ):
            continue
        if any(after[k] != before[k] for k in set(before) | set(after) if k.isdigit()):
            continue
        return dict(table, method="ruled-recovery")
    return None


def independent_grid(table):
    """A model-missed grid needs compact rows, not stacked numeric paragraphs."""
    content = [c for c in table["cells"] if c["text"].strip()]
    area = len(table["widths"]) * len(table["heights"])
    if not table.get("closedGrid") or len(content) < area * 0.7:
        return False
    if not any(c["r"] == 0 and any(ch.isalpha() for ch in c["text"]) for c in content):
        return False
    compact = sum(
        len(c["text"]) <= 120 and len(c["text"].splitlines()) <= 3 for c in content
    )
    if compact < len(content) * 0.9:
        return False
    for cell in content:
        lines = cell["text"].splitlines()
        if len(lines) > 1 and all(
            re.fullmatch(r"[\d.,%() +−-]+", line.strip()) for line in lines
        ):
            return False
    return True


def refine_predictions(item, page):
    """Separate repeated table headers and retain source-backed header spans.

    No sample IDs, reference annotations or generated text are used here.
    """
    from copy import deepcopy
    from layout_rows import repair_merged_rows
    from layout_headers import restore_underlined_headers
    from layout_sections import restore_section_headers

    item = deepcopy(item)
    data = item["data"]
    if not 0 < data["num_rows"] * data["num_cols"] <= 250000:
        raise LayoutError("The detected table exceeds the cell budget.")
    cells = data["table_cells"]
    box = model_box(item["prov"][0]["bbox"], page)
    # A full-width typographic rule is decoration, not a numeric cell prefix.
    if hasattr(page, "extract_words"):
        rules = {
            word["text"]
            for word in page.extract_words(x_tolerance=2, y_tolerance=3)
            if re.fullmatch(r"[-_=]{10,}", word["text"])
            and word["x1"] - word["x0"] >= (box[2] - box[0]) * 0.6
            and box[1] <= word["top"] <= box[3]
        }
        for cell in cells:
            for rule in rules:
                if cell["text"].startswith(rule + " "):
                    cell["text"] = cell["text"][len(rule) :].lstrip()

    by_row = defaultdict(list)
    for cell in cells:
        by_row[cell["start_row_offset_idx"]].append(cell)
    header_signatures = {}
    boundaries = [0]
    for row, entries in sorted(by_row.items()):
        signature = tuple(
            sorted(
                (c["start_col_offset_idx"], c["col_span"], "".join(c["text"].split()))
                for c in entries
                if c.get("column_header")
                and c["col_span"] > 1
                and any(ch.isalpha() for ch in c["text"])
            )
        )
        if not signature:
            continue
        if signature in header_signatures and row - boundaries[-1] >= 4:
            prior = [
                model_box(c["bbox"], page)[3] for c in by_row[row - 1] if c.get("bbox")
            ]
            current = [model_box(c["bbox"], page)[1] for c in entries if c.get("bbox")]
            crossing = any(
                c["start_row_offset_idx"]
                < row
                < c["start_row_offset_idx"] + c["row_span"]
                for c in cells
            )
            if prior and current and min(current) - max(prior) >= 5 and not crossing:
                boundaries.append(row)
        elif row <= 2:
            header_signatures[signature] = row
    boundaries.append(data["num_rows"])
    result = []
    for start, end in zip(boundaries, boundaries[1:]):
        part = deepcopy(item)
        pcells = [
            deepcopy(c) for c in cells if start <= c["start_row_offset_idx"] < end
        ]
        for cell in pcells:
            cell["start_row_offset_idx"] -= start
            cell["end_row_offset_idx"] -= start
        pdata = part["data"]
        pdata["table_cells"] = pcells
        pdata["num_rows"] = end - start
        if len(boundaries) > 2:
            bounds = [model_box(c["bbox"], page) for c in pcells if c.get("bbox")]
            part["prov"][0]["bbox"] = local_box(
                [
                    box[0],
                    max(box[1], min(b[1] for b in bounds) - 1),
                    box[2],
                    min(box[3], max(b[3] for b in bounds) + 1),
                ],
                page,
            )

        # Repeated dot leaders beside row labels are not an independent field.
        # Never collapse an ellipsis-containing value or a column with real data.
        for col in reversed(range(1, pdata["num_cols"])):
            entries = [
                c
                for c in pcells
                if c["start_col_offset_idx"] == col
                and c["col_span"] == 1
                and c["text"].strip()
            ]
            leaders = [c for c in entries if re.fullmatch(r"\.{8,}", c["text"].strip())]
            other = [c for c in entries if c not in leaders]
            if len(leaders) < 3 or len(leaders) < pdata["num_rows"] * 0.5:
                continue
            if any(
                not c.get("column_header") or any(ch.isdigit() for ch in c["text"])
                for c in other
            ):
                continue
            if any(
                any(
                    o["start_row_offset_idx"] == c["start_row_offset_idx"]
                    and o["start_col_offset_idx"] == col - 1
                    and o["text"].strip()
                    for o in pcells
                )
                for c in other
            ):
                continue
            updated = []
            for c in pcells:
                left = c["start_col_offset_idx"]
                right = left + c["col_span"]
                if left == col and c["col_span"] == 1:
                    if c in leaders or not c["text"].strip():
                        continue
                    c["start_col_offset_idx"] -= 1
                elif left > col:
                    c["start_col_offset_idx"] -= 1
                elif left <= col < right:
                    c["col_span"] -= 1
                c["end_col_offset_idx"] = c["start_col_offset_idx"] + c["col_span"]
                updated.append(c)
            pcells = updated
            pdata["table_cells"] = pcells
            pdata["num_cols"] -= 1
        restore_stub_header(pdata, page)
        result.append(
            restore_section_headers(
                restore_underlined_headers(repair_merged_rows(part, page), page), page
            )
        )
    from layout_source_rows import recover as recover_source_rows

    from layout_header_tree import recover as recover_header_tree

    from layout_section_rows import recover as recover_section_rows
    from layout_local_sections import recover as recover_local_sections
    from layout_columns import recover as recover_columns
    from layout_paragraph_rows import recover as recover_paragraphs
    from layout_header_spans import recover as recover_header_spans

    return [
        recover_header_spans(
            recover_paragraphs(
                recover_columns(
                    recover_local_sections(
                        recover_section_rows(
                            recover_source_rows(recover_header_tree(part, page), page), page
                        ),
                        page,
                    ),
                    page,
                ),
                page,
            ),
            page,
        )
        for part in result
    ]


def restore_stub_header(data, page):
    """Merge a stub under a multi-level header only across unruled gaps."""
    cells = data["table_cells"]
    rows = defaultdict(list)
    for c in cells:
        rows[c["start_row_offset_idx"]].append(c)
    header_end = 0
    while header_end in rows and any(c.get("column_header") for c in rows[header_end]):
        header_end += 1
    if not 2 <= header_end <= 4:
        return
    if not any(c["col_span"] > 1 for c in rows[0]):
        return
    stub = [
        c
        for c in cells
        if c["start_col_offset_idx"] == 0 and c["start_row_offset_idx"] < header_end
    ]
    nonempty = [c for c in stub if c["text"].strip()]
    if not nonempty or any(
        c["col_span"] != 1 or c["start_row_offset_idx"] + c["row_span"] > header_end
        for c in stub
    ):
        return
    if any(any(ch.isdigit() for ch in c["text"]) for c in nonempty):
        return
    # Only a header with a vacant top-left area is inferred, not an already
    # specified sequence of row labels.
    if any(c["start_row_offset_idx"] == 0 for c in nonempty):
        return
    bounds = [model_box(c["bbox"], page) for c in nonempty if c.get("bbox")]
    top_bounds = [model_box(c["bbox"], page) for c in rows[0] if c.get("bbox")]
    if not bounds or not top_bounds:
        return
    left, right = min(b[0] for b in bounds), max(b[2] for b in bounds)
    top, bottom = min(b[1] for b in top_bounds), max(b[3] for b in bounds)
    for edge in getattr(physical_page(page), "edges", []):
        if edge.get("orientation") == "h" and top < edge["top"] < bottom:
            if min(right, edge["x1"]) - max(left, edge["x0"]) >= 0.8 * (right - left):
                return
    merged = dict(nonempty[0])
    merged.update(
        start_row_offset_idx=0,
        end_row_offset_idx=header_end,
        row_span=header_end,
        text="\n".join(
            c["text"] for c in sorted(nonempty, key=lambda c: c["start_row_offset_idx"])
        ),
    )
    # Its original text bbox is the union, not the full inferred merged area.
    merged["bbox"] = local_box([left, min(b[1] for b in bounds), right, bottom], page)
    data["table_cells"] = [c for c in cells if c not in stub] + [merged]


@lru_cache(maxsize=1)
def converter_for(models):
    # Downloads are a separate provisioning step. A conversion cannot fetch
    # models or call a remote inference service.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    root = Path(models)
    required = [
        root / "docling-project--docling-layout-heron/model.safetensors",
        root
        / "docling-project--docling-models/model_artifacts/tableformer/accurate/tableformer_accurate.safetensors",
    ]
    if not all(p.is_file() for p in required):
        raise LayoutError(
            "The table recognition models are unavailable on this server."
        )
    options = PdfPipelineOptions(
        artifacts_path=root,
        do_ocr=False,
        enable_remote_services=False,
        document_timeout=150,
        accelerator_options=AcceleratorOptions(device="cpu", num_threads=2),
    )
    return DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=options),
        },
    )


def extract_layout_tables(source, indices, models, pages, native_extractor):
    if not indices:
        return {}
    from pypdf import PdfReader, PdfWriter
    from docling.datamodel.base_models import DocumentStream, ConversionStatus

    from layout_dense import dense_grid

    native, fast, remaining = {}, {}, []
    for index in indices:
        native[index] = native_extractor(pages[index])
        table = dense_grid(pages[index], native[index])
        if table is None:
            remaining.append(index)
        else:
            fast[index] = [table]
    cell_count = sum(
        len(t["widths"]) * len(t["heights"]) for tables in fast.values() for t in tables
    )
    if cell_count > 250000:
        raise LayoutError("The extracted tables exceed the cell budget.")
    if not remaining:
        return fast
    indices = remaining
    writer = PdfWriter()
    reader = PdfReader(source)
    for index in indices:
        writer.add_page(reader.pages[index])
    stream = io.BytesIO()
    writer.write(stream)
    stream.seek(0)
    result = converter_for(models).convert(
        DocumentStream(name="selected.pdf", stream=stream),
        max_num_pages=200,
        max_file_size=40 * 1024 * 1024,
    )
    if result.status != ConversionStatus.SUCCESS:
        raise LayoutError(
            "Table recognition did not finish completely. Try fewer pages."
        )
    grouped = defaultdict(list, fast)
    for item in result.document.tables:
        # A title/value pair is frequently labelled as a table by the layout
        # detector. The supported grid needs at least two rows and columns.
        if item.data.num_rows < 2 or item.data.num_cols < 2:
            continue
        if not item.prov:
            raise LayoutError("A detected table has no source page.")
        position = item.prov[0].page_no - 1
        if not 0 <= position < len(indices):
            raise LayoutError("A detected table has an invalid source page.")
        index = indices[position]
        predictions = refine_predictions(item.model_dump(), pages[index])
        if index not in native:
            try:
                native[index] = native_extractor(pages[index])
            except Exception:
                native[index] = []
        for prediction in predictions:
            try:
                from layout_grid import has_vertical_headers, recover_source_grid
                from layout_open import recover_open_grid

                table = (
                    recover_source_grid(prediction, pages[index])
                    if has_vertical_headers(prediction, pages[index])
                    else recover_open_grid(prediction, pages[index])
                )
                if table is None:
                    model = adapt_table(prediction, pages[index])
                    table = prefer_native(model, native[index])
            except LayoutError as error:
                table = (
                    recover_ruled_prediction(prediction, pages[index], native[index])
                    if "overlapping cells" in str(error)
                    else None
                )
                if table is None and "overlapping cells" in str(error):
                    from layout_grid import recover_source_grid

                    table = recover_source_grid(prediction, pages[index])
                if table is None:
                    raise
            cell_count += len(table["widths"]) * len(table["heights"])
            if cell_count > 250000:
                raise LayoutError("The extracted tables exceed the cell budget.")
            grouped[index].append(table)
    # Recover additional physical tables even when a page already has a model
    # table. Require a dense closed grid, a textual first row and no overlap.
    for index in indices:
        if index not in native:
            native[index] = native_extractor(pages[index])
        for table in native[index]:
            occupied = len(table["widths"]) * len(table["heights"])
            if not independent_grid(table):
                continue
            b = table["bbox"]
            if any(
                min(b[2], t["bbox"][2]) > max(b[0], t["bbox"][0])
                and min(b[3], t["bbox"][3]) > max(b[1], t["bbox"][1])
                for t in grouped[index]
            ):
                continue
            cell_count += occupied
            if cell_count > 250000:
                raise LayoutError("The extracted tables exceed the cell budget.")
            grouped[index].append(dict(table, method="ruled-recovery"))
    from layout_regions import recover_regions

    region_budget = 2
    for index in indices:
        if grouped[index] or region_budget <= 0:
            continue
        recovered, attempted = recover_regions(
            source, index, pages[index], converter_for(models), region_budget
        )
        region_budget -= attempted
        for table in recovered:
            cell_count += len(table["widths"]) * len(table["heights"])
            if cell_count > 250000:
                raise LayoutError("The extracted tables exceed the cell budget.")
            grouped[index].append(table)
    from layout_dense_rows import recover as recover_dense_rows, replace_fragments

    for index in indices:
        grouped[index] = replace_fragments(
            grouped[index], recover_dense_rows(pages[index])
        )
    if (
        sum(
            len(t["widths"]) * len(t["heights"])
            for tables in grouped.values()
            for t in tables
        )
        > 250000
    ):
        raise LayoutError("The extracted tables exceed the cell budget.")
    for tables in grouped.values():
        tables.sort(key=lambda t: (t["bbox"][1], t["bbox"][0]))
    return dict(grouped)

