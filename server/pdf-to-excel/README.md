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

Docling 2.150.0 with Heron layout detection and TableFormer V1 accurate structure is the primary native-page engine. Original PDF text is assigned to model-predicted cells; no language model rewrites values. TableFormer V2 and disabling PDF cell matching performed worse on the fixed comparison subset and are not used. pdfplumber supplies ruled geometry when dimensions, position and cell contents agree; clipped text can be expanded from corresponding physical cells without changing numerical tokens. Small aligned numeric tables have a conservative fallback and an explicit warning. Single-row/column model regions are excluded.

Native questionnaire forms with at least five clear vector checkbox frames can retain their text, source positions, editable checked/unchecked symbols and black source separator lines. Ambiguous marks are refused. Single-sheet exports use a shared coordinate grid and source-page print breaks; the form preview summarizes text rather than presenting that coordinate grid as data columns. Source-only form review is recorded separately from table references.

openpyxl writes real XLSX and literal strings. Stirling OfficeConvert handles rotated pages and emits a number-formatting warning. Scanned pages use RapidOCR 1.4.4 / PP-OCRv4 models plus OpenCV line-grid detection. If line-grid detection finds nothing, the same bundled OCR reader feeds the offline structure model; conservative aligned text can recover clearly aligned borderless scans. Ambiguous merged-cell geometry is refused. Short alphabetic OCR runs may gain missing spaces only when pixel gaps and two high-confidence rerecognitions agree on exactly the same letters. OCR/model confidence is not an accuracy guarantee. Complex structure fidelity remains a release acceptance concern; see the measured report.

The accuracy refinement cross-checks model cell text with original PDF glyphs before restoring punctuation/case; it never guesses a different number or word. PDF soft wraps are not added as extra Excel hard breaks. Repeated multi-column headers with a visible gap can separate tables that the detector fused. Header stub spans respect visible separator lines. Repeated dot leaders are treated as decoration, not a data column. Native extraction clips objects to the displayed MediaBox/CropBox intersection, and model coordinates are mapped back to the source origin, including offset and negative origins; off-page tables are not added by native recovery.

Continuous source column rules can remove a phantom column only when two nonnumeric header fragments are the sole collision and all body values keep their columns. Source paragraph starts and complete glyph coverage can repair a paragraph assigned to a neighboring row. A grouped heading may contract to its physical underline while repeated short stub headers recover their cross-row spans. Existing correct spans retain their original typography evidence; extending vertical labels or joining short CJK fragments requires a complete nonoverlapping physical grid and unchanged numeric anchors. Output row-height estimates use the larger of original glyph width and the actual exported font's metrics to prevent clipping after font substitution. These safeguards do not guarantee exact source typography or whole-corpus accuracy.

Conflicting model spans may fall back to a complete physical grid only when source characters are retained, digit counts match and bounding boxes agree. Additional model-missed grids require compact, dense cells and a textual header; stacked numeric paragraphs are excluded. Recovery emits a review warning. Ambiguous nested tables and unusual placeholder/leader layouts still need human review. Broad replacement of model structure by line geometry was evaluated and rejected because it merged distinct data values.

Open borders can be reconstructed from repeated physical rule ends within one predicted table. Recovery keeps the row count, limits any added column, preserves independent numeric cells and requires exact source character agreement. Bold section headings additionally require a full-width horizontal rule and no crossing separator. Numeric-range spaces require visible gaps and agreement on both endpoints.

A page with no detected table may retry at most two strongly bounded numeric regions per document, excluding adjacent chart columns. Region results must preserve every visible source character. Aligned year/month tables can recover geometrically overprinted glyphs; ordinary repeated letters are retained. Dense closed, unmerged source grids may avoid model inference only when source glyphs, occupancy and repeated numeric/text columns meet the conservative gate. These paths still need review against the original; output generation is not an accuracy claim.

A missed card grid can be recovered only with a complete regular outer grid and at least three source labels shared by every card. Smaller internal frames are excluded; mixed font heights use source baselines to retain reading order. Underlined multi-column headings require independent body anchors and an empty destination row. Rotated currency literals require exact numeric-string agreement with one complete source grid.

Source typography is restored only when glyph content, font family and geometry agree. Narrow verified headers receive bounded width padding. Overprinted blanks are removed only inside complete compact numeric/date runs; ordinary word gaps and dot leaders remain. Two alternating underlined field rows can recover complete fixed-width records only with source-character agreement. Blank merged cells require a complete physical grid matching every populated cell's text, position and span.

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
- Run the complete Python suite with `python -m unittest discover -s scripts/pdf-to-excel -p 'test_*.py'` in the configured conversion environment. Set `PDF_EXCEL_MODELS`, `PDF_EXCEL_OCR=true` and `STIRLING_URL` for actual model/OCR/rotation coverage. The suite includes conversion, bounds, source-backed rows/headers/grids/cards, region retry limits, dates, dense-grid routing, merged boundaries and conservative OCR spacing.
- `python scripts/pdf-to-excel/test_evaluation.py` validates the independent cell/structure scorer.
- `python scripts/pdf-to-excel/test_acceptance.py` checks strict source-reviewed reference evaluation, including omitted spaces, leading zeros, unexpected cells/sheets, merge loss, source hashes and stale outputs. Local references and review ledgers remain outside Git; missing references stay pending.
- `python scripts/pdf-to-excel/fixtures.py .pdf-excel-fixtures` then `pnpm exec playwright test --config playwright.pdf-excel.config.ts`. Set Python/OCR variables for the actual service. Build with the review flag first.
- `download-corpus.py <local-directory>/corpus` and `benchmark.py <local-directory>` keep all downloaded fixtures/output outside Git. Set `PDF_EXCEL_BENCHMARK_TIMEOUT=180` for the model engine, matching the service budget. Public does not imply redistribution permission.
- `compare-references.py <local-directory>` downloads pinned table-count/region/cell annotations; `evaluate-cells.py <local-directory>` compares actual output. Reference data is never used by the conversion engine. Exact text, whitespace-normalized text, spans and missing output are reported separately; this is not the official ICDAR scorer.

For a frozen comparison, use `compare-references.py <local-directory> --offline` with the already downloaded annotations. Evaluator v2 joins regions belonging to one table/page using their declared offsets. Re-score the baseline with the same evaluator; do not count a scorer correction as an engine improvement. `compare-runs.py BASELINE CANDIDATE OUTPUT.json` checks the same 200 identities, source hashes, runtime budget and evaluator version before reporting gains and regressions.

See the research and validation reports under `docs/pdf-to-excel-*.md` for acceptance limits. Do not market the corpus conversion rate as text/structure accuracy.

Source font metadata repair is limited to explicit WinAnsi Type1/CFF glyph-name evidence. The bounded CFF1 reader supports custom charset formats 0/1/2; CID fonts, unknown charsets and malformed ranges remain untouched. A simple Type1 font with a wide declared Unicode code space is eligible only when every actual mapping uses a single-byte source code. Repairs use a temporary PDF inside the output job directory; the uploaded original and rendered page content remain unchanged. Unknown fonts keep their existing extraction path. Separate worksheets use source page orientation and one-page printing; a combined worksheet remains multi-page.

Sectioned numeric rows require complete native-word coverage, repeated column anchors, physical top/bottom rules and unambiguous indentation or typography. Closed multiline grids and incomplete rows keep the existing interpretation. Complete-word header recovery preserves an already verified header before attempting its fallback. Typography recovery verifies a whole ordered source phrase and never changes literal values; range gaps and superscript boundaries are checked separately.
