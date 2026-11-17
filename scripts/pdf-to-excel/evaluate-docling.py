"""Research-only, offline Docling benchmark. Does not enable production routing.

Install Docling in a separate environment and prefetch models before running.
Arguments: corpus parent, model directory, output directory, optional comma IDs.
"""

import json
import os
from pathlib import Path
import shutil
import sys
import time

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["DOCLING_TELEMETRY_ENABLED"] = "false"

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TableStructureV2Options,
)
from docling.datamodel.accelerator_options import AcceleratorOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from convert import write_workbook


def main():
    root, models, destination = map(Path, sys.argv[1:4])
    ids = (
        set(sys.argv[4].split(","))
        if len(sys.argv) > 4
        else {
            p.name.removesuffix("-str.xml")
            for p in (root / "references").glob("*-str.xml")
        }
    )
    (destination / "outputs").mkdir(parents=True, exist_ok=True)
    (destination / "references").mkdir(exist_ok=True)
    options = PdfPipelineOptions(
        artifacts_path=models,
        do_ocr=False,
        enable_remote_services=False,
        document_timeout=90,
        accelerator_options=AcceleratorOptions(device="cpu", num_threads=4),
    )
    if os.environ.get("PDF_EXCEL_TABLE_MODEL") == "v2":
        options.table_structure_options = TableStructureV2Options()
    if os.environ.get("PDF_EXCEL_CELL_MATCHING") == "false":
        options.table_structure_options.do_cell_matching = False
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    manifest = json.loads((root / "corpus/manifest.json").read_text())
    rows = []
    for item in manifest:
        if item["id"] not in ids:
            continue
        started = time.monotonic()
        row = {"id": item["id"]}
        for kind in ("str", "reg"):
            shutil.copyfile(
                root / "references" / (item["id"] + "-" + kind + ".xml"),
                destination / "references" / (item["id"] + "-" + kind + ".xml"),
            )
        try:
            result = converter.convert(
                root / "corpus" / item["file"],
                max_num_pages=200,
                max_file_size=30 * 1024 * 1024,
            )
            result.document.save_as_json(
                destination / "outputs" / (item["id"] + ".json")
            )
            tables = []
            page_counts = {}
            for table in result.document.tables:
                if not table.prov or not table.data.num_rows or not table.data.num_cols:
                    continue
                page = table.prov[0].page_no
                page_counts[page] = page_counts.get(page, 0) + 1
                box = table.prov[0].bbox
                tables.append(
                    {
                        "page": page,
                        "index": page_counts[page],
                        "widths": [box.width / table.data.num_cols]
                        * table.data.num_cols,
                        "heights": [box.height / table.data.num_rows]
                        * table.data.num_rows,
                        "cells": [
                            dict(
                                r=c.start_row_offset_idx,
                                c=c.start_col_offset_idx,
                                rs=c.row_span,
                                cs=c.col_span,
                                text=c.text,
                            )
                            for c in table.data.table_cells
                        ],
                    }
                )
            if not tables:
                raise ValueError("No tables")
            write_workbook(
                tables, destination / "outputs" / (item["id"] + ".xlsx"), "tables"
            )
            row.update(status="converted", tables=len(tables))
        except Exception as error:
            row.update(
                status="refused", reason=type(error).__name__ + ": " + str(error)[:400]
            )
        row["seconds"] = round(time.monotonic() - started, 3)
        rows.append(row)
        (destination / "benchmark.json").write_text(
            json.dumps({"results": rows}, indent=2)
        )
        print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
