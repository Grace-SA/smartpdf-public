# Isolated structured OCR safety probe

**Research only. Not imported by the application, not an OCR fallback, and not a release gate. No production integration.**

## Result

A previously promising single ruled-table experiment did not generalize. First annotated pages from 12 independent ICDAR2013 source PDFs contain 19 annotated table regions, 1,245 cells and 15 merged cells. This probe emits **zero usable tables on all 12 pages**: 7 incomplete-grid refusals, 3 no-grid refusals, and 2 cell-budget refusals. This is 0/12 page coverage, NOT 100% accuracy or a successful benchmark. Refusal avoids inventing structure here but is not useful general conversion. Rasterized digital PDFs are not genuine scans.

An additional scan-derived W3C OCR-example PDF, manually reviewed as having no table, produces no false table. That is only a negative control. Its existing OCR text layer is ignored; only the rendered page enters inference. Independently labeled **positive real scanned tables remain a gap**. No claim about broad scanning accuracy is supported.

The public examples include merged headers and multicolumn narrative (`us-001`), a table without vertical rulings embedded in narrative (`us-003`), and pages with multiple tables. Original ICDAR annotations may contain known errors; this is not the corrected ICDAR2013.c benchmark. No model is trained or tuned on these labels. The first annotated page rule was fixed before inference. No successful pages were cherry-picked.

## What is measured

Inference sees only raster pixels and Tesseract TSV, never XML labels. Scoring checks table count, row/column shape and whether merges are required, then exact normalized cell text only for shape/span-compatible single-table predictions. `shape_span_compatible` is a necessary condition, **not proof of spatial or semantic structure accuracy**. `incompatible_grid_acceptance` detects obvious unsafe acceptances but cannot establish complete safety. We do not score OCR confidence as structure quality. XML bounds are text bounds, not cell boundaries, so no misleading grid IoU is reported.

This runner evaluates the full-page ruled-grid candidate without deskew. The earlier single-source deskew/crop experiment was not a general system and is not included in these metrics. Refused pages are failures of coverage, not silently omitted from the denominator. The existing configured PaddleOCR-VL engine is not benchmarked by this tool; do not claim relative superiority.

## Review and bounds

Synthetic tests exposed an unsafe 95% separator-completeness tolerance: a short missing segment was accepted. Raised to99.5% and added a regression. This is conservative rejection, not a calibrated correctness guarantee. Tests also cover a fully merged separator, no grid, pixel and cell budgets. Fixed an unclosed TSV handle. Six synthetic unit tests pass. No public/private assets are used in these tests.

Probe caps decoded images at16M pixels, cells at200, TSV files at10MB, per-cell OCR at10s and checks a45s crop-page budget between calls; whole-page OCR has45s timeout. Rendering/decoding occurs before some checks, and a crop can run beyond the inter-call budget by up to10s. These are research bounds, NOT hardened untrusted-upload isolation. Run only reviewed public files in a disposable offline environment, with an external OS/container timeout and memory cap. No service endpoint, package hook or CI job imports this code.

No product regression suite was run because this adds only isolated research tools. Unit tests, full12-page rerun, and scan control were executed locally. A full repository checker was attempted on the available sparse workspace; missing pre-existing assets prevent a whole-tree pass. Git publication must retain the original base tree and add only these reviewed text files. No deployment is authorized by these results.

## Reproduce

Python3.12; Tesseract5.5.0 with English data; the four Python versions are pinned in requirements.txt. This is an environment record, not a cryptographic dependency lock. Install in an isolated environment from official package registries. Exact OCR results can vary with engine/data/platform versions.

Obtain the public upstream files separately only after your own applicable-use review. No automatic download is performed. `source-manifest.json` gives the immutable Camelot repository revision, PDF paths and PDF/XML SHA256s. Reference XML files are named `<id>-str.xml` in the same upstream competition-dataset directory. Put PDFs and a copy of source-manifest.json named manifest.json in CORPUS, and the XML files in REFERENCES. Hash checks run before parsing.

```sh
python -m unittest -v test_probe
python evaluate.py --corpus CORPUS --references REFERENCES --output /tmp/ocr-grid-run
```

The output directory must not already exist. It contains local raster/TSV/crops and aggregate metrics. **Never commit that directory or recognition text.** Included metrics.json contains only aggregate per-page counts, source hashes and timings, not cell text.

Negative control source:
https://www.w3.org/WAI/WCAG22/working-examples/pdf-ocr/ocr-example.pdf

SHA256: `7a161be656c7e82986a1959890eadbdcd0876e15e01b28fd00900190de15eed5`

```sh
python negative_control.py --pdf /path/ocr-example.pdf --sha256 7a161be656c7e82986a1959890eadbdcd0876e15e01b28fd00900190de15eed5 --output /tmp/ocr-negative-run
```

## Source and license review

ICDAR competition and format: https://tamirhassan.com/html/competition.html and https://tamirhassan.com/html/competition/dataset-format.html

Annotation correction context: https://huggingface.co/datasets/bsmock/ICDAR-2013.c

The Apache2.0 license on associated dataset tools does not automatically license every source PDF. Camelot's code license likewise does not establish redistribution rights for all fixtures. No dataset-wide redistribution clearance was established. Consequently **no PDF, XML annotation, image, cell transcription or extracted text is included**. Only original code, public source pointers/hashes and aggregate measurements are committed. The W3C scan is also not redistributed. Dependencies retain their own licenses; they are not vendored.

Next gate: obtain independently reviewed positive scan/table-layout labels, support borderless and merged structures plus mixed reading order, and run matched-resource comparison against the configured structured OCR before considering integration. Current results justify rejecting this prototype as a general engine.
