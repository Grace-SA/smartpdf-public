"""Bounded recovery for numeric tables sharing a physical frame with charts."""

from collections import Counter
from statistics import median
from io import BytesIO

from collections import defaultdict
import re
from pdfplumber.utils import cluster_objects
from layout_tables import physical_page, visible_box


def candidates(page):
    page = physical_page(page.crop(tuple(visible_box(page))))
    regions = {}
    for grid in page.find_tables():
        bycol = defaultdict(list)
        for b in grid.cells:
            bycol[(round(b[0], 1), round(b[2], 1))].append(b)
        for (left, right), boxes in bycol.items():
            if (
                len(boxes) < 3
                or right - left < page.width * 0.35
                or right - left > page.width * 0.85
            ):
                continue
            top, bottom = min(b[1] for b in boxes), max(b[3] for b in boxes)
            if bottom - top < page.height * 0.35:
                continue
            words = page.crop((left, top, right, bottom)).extract_words(
                x_tolerance=2, y_tolerance=3
            )
            good_rows = []
            for row in cluster_objects(
                words, lambda w: (w["top"] + w["bottom"]) / 2, 3
            ):
                numeric = [
                    w
                    for w in row
                    if re.fullmatch(r"[\d.,%()+−–—\-]+", w["text"])
                    and any(c.isdigit() for c in w["text"])
                ]
                if len(numeric) >= 3 and any(
                    any(c.isalpha() for c in w["text"]) for w in row
                ):
                    good_rows.append(row)
            if len(good_rows) >= 5:
                # A coarse enclosing frame can include a contact footer. Stop
                # only at a full-width physical rule just below the last data
                # row, never at a model-predicted text boundary.
                last_bottom = max(w["bottom"] for row in good_rows for w in row)
                line_height = median(
                    w["bottom"] - w["top"] for row in good_rows for w in row
                )
                closers = [
                    e["top"]
                    for e in page.edges
                    if e["orientation"] == "h"
                    and left - 3 <= e["x0"] <= left + 3
                    and e["x1"] >= right - 3
                    and last_bottom
                    <= e["top"]
                    <= min(bottom, last_bottom + 2 * line_height)
                ]
                if closers:
                    first = min(closers)
                    bottom = median(y for y in closers if y <= first + 3)
                regions[(left, top, right, bottom)] = len(good_rows)
    return sorted(regions, key=lambda b: regions[b], reverse=True)[:2]


def matching_source(tables, page, region):
    """A region retry cannot silently drop source labels or introduce values."""
    if not tables or any(
        len(table["widths"]) < 3 or len(table["heights"]) < 6 for table in tables
    ):
        return False
    source = Counter(
        ch
        for glyph in page.chars
        if region[0] - 2 <= (glyph["x0"] + glyph["x1"]) / 2 <= region[2] + 2
        and region[1] - 2 <= (glyph["top"] + glyph["bottom"]) / 2 <= region[3] + 2
        for ch in glyph["text"]
        if not ch.isspace()
    )
    output = Counter(
        ch
        for table in tables
        for cell in table["cells"]
        for ch in cell["text"]
        if not ch.isspace()
    )
    return bool(source) and source == output


def recover_regions(source, index, page, converter, budget):
    """Retry at most the remaining document-wide region budget."""
    from pypdf import PdfReader, PdfWriter
    from docling.datamodel.base_models import DocumentStream, ConversionStatus
    from layout_tables import adapt_table, refine_predictions

    if budget <= 0 or page.rotation:
        return [], 0
    boxes = candidates(page)
    if not boxes:
        return [], 0
    original = PdfReader(source).pages[index]
    # Pypdf crop coordinates below are valid for unrotated, zero-origin media.
    # Other origins keep the existing extraction path until separately verified.
    if tuple(original.mediabox.lower_left) != (0, 0):
        return [], 0
    tables, attempted, used = [], 0, []
    for box in boxes:
        if attempted >= budget:
            break
        if any(
            min(box[2], b[2]) > max(box[0], b[0])
            and min(box[3], b[3]) > max(box[1], b[1])
            for b in used
        ):
            continue
        attempted += 1
        writer = PdfWriter()
        writer.add_page(original)
        cropped_pdf = writer.pages[0]
        cropped_pdf.cropbox.lower_left = (box[0], page.height - box[3])
        cropped_pdf.cropbox.upper_right = (box[2], page.height - box[1])
        stream = BytesIO()
        writer.write(stream)
        stream.seek(0)
        result = converter.convert(
            DocumentStream(name="region.pdf", stream=stream),
            max_num_pages=1,
            max_file_size=40 * 1024 * 1024,
        )
        if result.status != ConversionStatus.SUCCESS:
            continue
        cropped_page = page.crop(box)
        region_tables = []
        for prediction in result.document.tables:
            if prediction.data.num_rows < 2 or prediction.data.num_cols < 2:
                continue
            for item in refine_predictions(prediction.model_dump(), cropped_page):
                region_tables.append(adapt_table(item, cropped_page))
        if matching_source(region_tables, page, box):
            tables.extend(
                dict(table, method="layout-region") for table in region_tables
            )
            used.append(box)
    return tables, attempted
