"""Offline structure recognition for scans without a complete visible grid.

The pinned Docling pipeline uses the same bundled RapidOCR reader as the ruled
scan path. No additional models, OCR packages or remote services are provisioned
during conversion. OCR strings remain uncorrected recognition results.
"""

import io
import math
import os
from collections import defaultdict
from functools import lru_cache
from itertools import pairwise
from pathlib import Path

from layout_tables import LayoutError, adapt_table, visible_box


@lru_cache(maxsize=1)
def scan_converter(models, reader):
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    root = Path(models)
    required = [
        root / "docling-project--docling-layout-heron/model.safetensors",
        root
        / "docling-project--docling-models/model_artifacts/tableformer/accurate/tableformer_accurate.safetensors",
    ]
    if not all(path.is_file() for path in required):
        raise LayoutError(
            "The table recognition models are unavailable on this server."
        )
    import numpy as np
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        OcrMode,
        PdfPipelineOptions,
        RapidOcrOptions,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.models.base_ocr_model import BaseOcrModel
    from docling.models.stages.ocr.rapid_ocr_model import RapidOcrModel
    from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline

    class BundledRapidOcr(RapidOcrModel):
        def __init__(self, artifacts_path, options, accelerator_options):
            BaseOcrModel.__init__(
                self,
                enabled=True,
                artifacts_path=artifacts_path,
                options=options,
                accelerator_options=accelerator_options,
            )
            self.scale = options.scale

        def _read(self, image):
            result, _ = reader(np.asarray(image))
            from ocr_spaces import recover_spaces

            return recover_spaces(np.asarray(image), result, reader)

    class ScanPipeline(StandardPdfPipeline):
        def _make_ocr_model(self, art_path):
            return BundledRapidOcr(
                art_path,
                self.pipeline_options.ocr_options,
                self.pipeline_options.accelerator_options,
            )

    options = PdfPipelineOptions(
        artifacts_path=Path(models),
        do_ocr=True,
        generate_parsed_pages=True,
        enable_remote_services=False,
        document_timeout=120,
        accelerator_options=AcceleratorOptions(device="cpu", num_threads=2),
        ocr_options=RapidOcrOptions(mode=OcrMode.FULL_PAGE, scale=3),
    )
    return DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_cls=ScanPipeline, pipeline_options=options
            )
        },
    )


def reject_inverted_scan_columns(item, page_height):
    """Refuse a proved local contradiction, never infer or repair a column.

    Only adjacent eligible single-span cells in the same model row are checked.
    Their OCR text boxes must overlap vertically and be strictly reversed in x.
    Missing boxes, spans and disjoint text lines are not visibility/order proofs.
    Passing this necessary check does not establish table correctness.
    """
    rows = defaultdict(list)
    for cell in item["data"]["table_cells"]:
        if cell.get("row_span", 1) != 1 or cell.get("col_span", 1) != 1:
            continue
        if not cell["text"].strip() or cell.get("bbox") is None:
            continue
        box = cell["bbox"]
        if box.get("coord_origin") not in ("TOPLEFT", "BOTTOMLEFT"):
            raise LayoutError("Scanned cell geometry has an unsupported origin.")
        coords = [box.get(key) for key in ("l", "t", "r", "b")]
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in coords
        ):
            raise LayoutError("Scanned cell geometry is invalid.")
        left, top, right, bottom = coords
        if box["coord_origin"] == "BOTTOMLEFT":
            top, bottom = page_height - top, page_height - bottom
        if right <= left or bottom <= top:
            raise LayoutError("Scanned cell geometry is invalid.")
        rows[cell["start_row_offset_idx"]].append(
            (cell["start_col_offset_idx"], left, top, right, bottom)
        )
    for cells in rows.values():
        cells.sort(key=lambda cell: cell[0])
        for earlier, later in pairwise(cells):
            # Both axes need positive separation/overlap: equality and tiny
            # overlapping word boxes do not justify a geometric contradiction.
            if (
                earlier[0] < later[0]
                and earlier[1] > later[3]
                and min(earlier[4], later[4]) > max(earlier[2], later[2])
            ):
                raise LayoutError(
                    "Scanned table columns conflict with recognized text positions. "
                    "Conversion stopped rather than exporting values in wrong columns."
                )


def extract_scan_layout_tables(source, index, models, page, reader):
    from docling.datamodel.base_models import ConversionStatus, DocumentStream
    from pypdf import PdfReader, PdfWriter

    view = visible_box(page)
    if (view[2] - view[0]) * (view[3] - view[1]) * 9 > 20_000_000:
        raise LayoutError("The scanned page is too large for structure recognition.")
    writer = PdfWriter()
    writer.add_page(PdfReader(source).pages[index])
    stream = io.BytesIO()
    writer.write(stream)
    stream.seek(0)
    result = scan_converter(models, reader).convert(
        DocumentStream(name="scan.pdf", stream=stream),
        max_num_pages=1,
        max_file_size=40 * 1024 * 1024,
    )
    if result.status != ConversionStatus.SUCCESS:
        raise LayoutError("Scanned table recognition did not finish completely.")
    tables = []
    for item in result.document.tables:
        if item.data.num_rows < 2 or item.data.num_cols < 2:
            continue
        raw = item.model_dump()
        table = adapt_table(raw, page, native_text=False)
        reject_inverted_scan_columns(raw, view[3] - view[1])
        table["method"] = "ocr-layout"
        tables.append(table)
    tables.sort(key=lambda t: (t["bbox"][1], t["bbox"][0]))
    if not tables:
        from types import SimpleNamespace

        from text_tables import conservative_aligned_tables

        words = []
        parsed = result.pages[0].parsed_page
        if parsed is not None:
            for cell in parsed.textline_cells:
                if not cell.from_ocr or cell.confidence < 0.85:
                    # Do not silently drop uncertain lines to create alignment.
                    return []
                box = cell.rect.to_bounding_box().to_top_left_origin(
                    result.pages[0].size.height
                )
                words.append(
                    dict(
                        text=cell.text,
                        x0=box.l + view[0],
                        x1=box.r + view[0],
                        top=box.t + view[1],
                        bottom=box.b + view[1],
                    )
                )
            tables = conservative_aligned_tables(
                SimpleNamespace(extract_words=lambda **_: words, images=[True])
            )
            for table in tables:
                table["method"] = "ocr-aligned"
    return tables
