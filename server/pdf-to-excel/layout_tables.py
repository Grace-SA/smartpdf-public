"""Offline layout/structure adapter; models never generate cell text."""

from collections import Counter, defaultdict
import math
from statistics import median
from functools import lru_cache
import io
import os
from pathlib import Path


class LayoutError(Exception):
    pass


def top_box(box, height):
    if box.get("coord_origin") == "BOTTOMLEFT":
        return [box["l"], height - box["t"], box["r"], height - box["b"]]
    return [box["l"], box["t"], box["r"], box["b"]]


def overlap(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0, min(a[3], b[3]) - max(a[1], b[1])
    )
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / union if union > 0 else 0


def adapt_table(item, page):
    data = item["data"]
    rows, columns = data["num_rows"], data["num_cols"]
    if not rows or not columns or rows * columns > 250000:
        raise LayoutError("The detected table exceeds the cell budget.")
    box = top_box(item["prov"][0]["bbox"], page.height)
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
        cells.append({"r": r, "c": c, "rs": rs, "cs": cs, "text": cell["text"]})
        if cell.get("bbox") and cell["text"].strip():
            cb = top_box(cell["bbox"], page.height)
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


def prefer_native(model, native):
    """Use exact ruled geometry only when independent structure agrees in size."""

    def texts(table):
        return Counter(
            "".join(c["text"].split()) for c in table["cells"] if c["text"].strip()
        )

    for candidate in native:
        if (
            len(candidate["widths"]) == len(model["widths"])
            and len(candidate["heights"]) == len(model["heights"])
            and overlap(candidate["bbox"], model["bbox"]) >= 0.7
            and texts(candidate) == texts(model)
        ):
            return candidate
    return model


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
    grouped = defaultdict(list)
    native = {}
    cell_count = 0
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
        model = adapt_table(item.model_dump(), pages[index])
        if index not in native:
            try:
                native[index] = native_extractor(pages[index])
            except Exception:
                native[index] = []
        table = prefer_native(model, native[index])
        cell_count += len(table["widths"]) * len(table["heights"])
        if cell_count > 250000:
            raise LayoutError("The extracted tables exceed the cell budget.")
        grouped[index].append(table)
    for tables in grouped.values():
        tables.sort(key=lambda t: (t["bbox"][1], t["bbox"][0]))
    return dict(grouped)
