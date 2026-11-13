"""Corpus robustness run. Cell/structure accuracy is scored separately."""

import concurrent.futures, hashlib, json, os, subprocess, sys, time
from pathlib import Path
from xml.etree import ElementTree as ET
import zipfile

root = Path(sys.argv[1])
output = root / "outputs"
output.mkdir(exist_ok=True)
manifest = json.loads((root / "corpus/manifest.json").read_text())
runner = Path(__file__).resolve().parents[2] / "server/pdf-to-excel/convert.py"
timeout = int(os.environ.get("PDF_EXCEL_BENCHMARK_TIMEOUT", "35"))
workers = int(os.environ.get("PDF_EXCEL_BENCHMARK_WORKERS", "3"))


def fingerprint():
    return {
        name: hashlib.sha256((runner.parent / name).read_bytes()).hexdigest()
        for name in (
            "convert.py",
            "layout_tables.py",
            "layout_rows.py",
            "layout_headers.py",
            "layout_cards.py",
            "layout_sections.py",
            "layout_ranges.py",
            "layout_regions.py",
            "layout_open.py",
            "layout_dense.py",
            "layout_dates.py",
            "layout_alternating.py",
            "layout_typography.py",
            "layout_blank.py",
            "source_glyphs.py",
            "layout_dense_rows.py",
            "layout_source_rows.py",
            "source_phrases.py",
            "source_fonts.py",
            "cff_names.py",
            "layout_header_tree.py",
            "layout_section_rows.py",
            "layout_columns.py",
            "layout_paragraph_rows.py",
            "layout_header_spans.py",
            "layout_forms.py",
            "form_workbook.py",
            "xlsx_form_rules.py",
            "ocr_leaders.py",
            "ocr_monospace.py",
            "ocr_punctuation.py",
            "ocr_spaces.py",
            "layout_grid.py",
            "ocr_layout.py",
            "text_tables.py",
            "requirements-lock.txt",
            "models.json",
        )
    }


runtime = {
    "python": sys.version.split()[0],
    "timeoutSeconds": timeout,
    "workers": workers,
    "modelsEnabled": bool(os.environ.get("PDF_EXCEL_MODELS")),
    "stirlingEnabled": bool(os.environ.get("STIRLING_URL")),
    "engineSha256": fingerprint(),
}


def case(item):
    started = time.monotonic()
    out = output / (item["id"] + ".xlsx")
    source = root / "corpus" / item["file"]
    row = {"id": item["id"], "sha256": item["sha256"]}
    try:
        out.unlink(missing_ok=True)
        if hashlib.sha256(source.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("Source hash mismatch")
        p = subprocess.run(
            [
                sys.executable,
                str(runner),
                str(source),
                str(out),
                json.dumps({"ocr": True}),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            env=dict(os.environ, OMP_NUM_THREADS="2"),
        )
        result = json.loads(p.stdout.decode().strip().split("\n")[-1])
        if p.returncode:
            row.update(
                status="refused", reason=result.get("error", "conversion failed")
            )
        else:
            with zipfile.ZipFile(out) as z:
                sheets = [
                    ET.fromstring(z.read(n))
                    for n in z.namelist()
                    if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")
                ]
                if not sheets or any(
                    e.tag.endswith("}f") for t in sheets for e in t.iter()
                ):
                    raise ValueError("Unsafe or missing worksheets")
                nonempty = sum(
                    1
                    for t in sheets
                    for e in t.iter()
                    if e.tag.endswith("}t") and e.text
                )
                if not nonempty:
                    raise ValueError("Empty workbook")
            row.update(
                status="converted",
                tables=result["tables"],
                sheets=result["sheets"],
                missingPages=result["missingPages"],
                ocrPages=result["ocrPages"],
                nonemptyCells=nonempty,
                bytes=out.stat().st_size,
                outputSha256=hashlib.sha256(out.read_bytes()).hexdigest(),
            )
    except subprocess.TimeoutExpired:
        row.update(
            status="timeout",
            reason=f"{timeout}-second benchmark budget (service budget is 180 seconds)",
        )
    except Exception as e:
        row.update(status="error", reason=type(e).__name__ + ": " + str(e))
    if row["status"] != "converted":
        out.unlink(missing_ok=True)
    row["seconds"] = round(time.monotonic() - started, 3)
    return row


results = []
with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
    for row in pool.map(case, manifest):
        results.append(row)
        (root / "benchmark.json").write_text(
            json.dumps(
                {
                    "scope": "200 public PDFs; no ground-truth accuracy claim",
                    "runtime": runtime,
                    "results": results,
                },
                indent=2,
            )
        )
        print(len(results), row["id"], row["status"], row["seconds"], flush=True)
from collections import Counter

if fingerprint() != runtime["engineSha256"]:
    raise RuntimeError("Engine changed during the benchmark; results must be rerun.")
summary = dict(Counter(r["status"] for r in results))
(root / "benchmark-summary.json").write_text(json.dumps(summary, indent=2))
print(summary)
