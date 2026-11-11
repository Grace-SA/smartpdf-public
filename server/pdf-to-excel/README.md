# PDF → XLSX service

This is a separate service and URL namespace from Excel → PDF. It does not alter Word/PPT/Excel → PDF or the PDF → PPT task.

## Local development

1. Python 3.12: create a virtual environment. On Linux first install `torch==2.15.0 torchvision==0.29.1` from `https://download.pytorch.org/whl/cpu` with pip's `--index-url` option; then install `-r server/pdf-to-excel/requirements-lock.txt`. This avoids CUDA dependencies. macOS uses the ordinary pinned wheels.
2. Run `python scripts/pdf-to-excel/prepare-models.py .pdf-excel-models`. This setup step downloads about 367 MiB of pinned Heron/TableFormer assets and verifies every SHA-256 in `models.json`. Set `PDF_EXCEL_MODELS` to that directory. Conversion uses local models with remote inference and Hugging Face network access disabled. OCR weights ship inside the pinned RapidOCR wheel.
3. Set `PDF_EXCEL_PYTHON` to that environment's Python executable. Set `PDF_EXCEL_OCR=true` to enable OCR, and `STIRLING_URL` to your internal Stirling 3.2.2 API for rotated tables. Optionally supply `STIRLING_API_KEY` through the environment. No credentials go to the browser.
4. Run `pnpm pdf-excel:serve` (127.0.0.1:4290), then `pnpm dev`. Open `/pdf-to-excel/`. For a built preview use `VITE_ENABLE_PDF_EXCEL=true pnpm build`.
5. Server URL requests use `/api/pdf-to-excel/`. Vite preserves the original Host for same-origin checks. A deployment proxy must do the same, or set `PDF_EXCEL_ORIGIN` to the exact public HTTPS origin.

Production discovery defaults OFF. Enabling the frontend flag alone does not provide a conversion backend. `NODE_ENV=production` refuses admission without the layout model directory. The lightweight development path without models is retained for comparison, and is not the recommended production engine.

## Deployment contract (not deployed; container verification in CI)

Build the provided Dockerfile from the repository root. The compose example supplies CPU, memory, process and ephemeral-disk bounds. Run one service process per container, behind the site's HTTPS reverse proxy. Keep Stirling private and enforce network egress restrictions to that internal destination only. The image should be digest-pinned and scanned in the deployment pipeline before release; the provided base tag is not an immutable production artifact.

Job/session state is in memory. Use one replica or stable session affinity; round-robin routing across independent replicas will not work. Horizontal scaling requires shared state and a shared queue, which are outside this candidate. CI includes a Linux container smoke test with networking disabled, a read-only root filesystem and the stated resource bounds; its actual result is recorded by the PR workflow, not assumed from the Dockerfile.

`PDF_EXCEL_REGION` must describe the actual region, not a guessed location. Secure session cookies require HTTPS. Source PDFs are removed immediately after a successful conversion; outputs and failed-job metadata expire. Cancel/delete/close terminates the child process and removes its directory. Ephemeral `/tmp` must be cleared on restart: a hard process or host crash cannot execute JavaScript cleanup. Do not put uploaded documents into durable storage or backup. A healthy process runs the expiry sweep at most every 10 seconds.

The gateway serializes conversion, admits at most 16 jobs globally / 2 per session, caps input/output at 30 MiB, upload at 120 seconds, conversion at 180 seconds and parser stdout at 2 MiB. Docling has an additional 150-second document budget. Parser diagnostics are discarded. Sessions expire after 14 minutes, leaving the cleanup sweep within the 15-minute retention notice. Python checks 200 pages / 250,000 cells; the example container has a 4 GiB memory bound that still requires production load testing.

## Engine decision

Docling 2.150.0 with Heron layout detection and TableFormer V1 accurate structure is the primary native-page engine. Original PDF text is assigned to model-predicted cells; no language model rewrites values. TableFormer V2 and disabling PDF cell matching performed worse on the fixed comparison subset and are not used. pdfplumber supplies exact ruled geometry only when table size, position and the complete cell-text multiset agree with the model. Small aligned numeric tables have a conservative fallback and an explicit warning. Single-row/column model regions are excluded.

openpyxl writes real XLSX and literal strings. Stirling OfficeConvert handles rotated pages and emits a number-formatting warning. Scanned pages use RapidOCR 1.4.4 / PP-OCRv4 models plus OpenCV line-grid detection. This OCR path supports clearly ruled tables, not arbitrary unruled scans; ambiguous merged-cell geometry is refused. OCR/model confidence is not an accuracy guarantee. Complex structure fidelity remains a release acceptance concern; see the measured report.

All extracted values are strings: leading zeros, long integers and formula-like content remain unchanged. Consumers may deliberately convert selected cells to numbers in Excel. Original spreadsheet formulas cannot be reconstructed from rendered PDFs.

## API

- `GET /session`: HttpOnly SameSite session cookie, availability, OCR capability, region, retention.
- `POST /jobs?pages=1-3,5&layout=tables&ocr=true`: raw `application/pdf` body; returns 202 job ID. `layout=single` stacks tables with page/table separators without semantic merging.
- `GET /jobs/:id`: state, safe error, table counts, warnings, bounded preview.
- `GET /jobs/:id/download`: verified XLSX. Cross-session access returns 404.
- `DELETE /jobs/:id`: terminate and delete.

No filename, password, extracted text or document analytics is sent to third parties.

## Tests

- `pnpm test` and `pnpm typecheck`.
- `python scripts/pdf-to-excel/test_conversion.py`; set `STIRLING_URL` for the real rotated-table test. Missing OCR/Stirling explicitly skips corresponding integrations.
- `python scripts/pdf-to-excel/test_layout.py` and `python scripts/pdf-to-excel/test_evaluation.py` validate model bounds and the independent scoring logic.
- `python scripts/pdf-to-excel/fixtures.py .pdf-excel-fixtures` then `pnpm exec playwright test --config playwright.pdf-excel.config.ts`. Set Python/OCR variables for the actual service. Build with the review flag first.
- `download-corpus.py <local-directory>/corpus` and `benchmark.py <local-directory>` keep all downloaded fixtures/output outside Git. Set `PDF_EXCEL_BENCHMARK_TIMEOUT=180` for the model engine, matching the service budget. Public does not imply redistribution permission.
- `compare-references.py <local-directory>` downloads pinned table-count/region/cell annotations; `evaluate-cells.py <local-directory>` compares actual output. Reference data is never used by the conversion engine. Exact text, whitespace-normalized text, spans and missing output are reported separately; this is not the official ICDAR scorer.

See the research and validation reports under `docs/pdf-to-excel-*.md` for acceptance limits. Do not market the corpus conversion rate as text/structure accuracy.
