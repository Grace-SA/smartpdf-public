# PDF to Excel: independent quality baseline

This is **local evaluation tooling**, not a published converter. It creates
original synthetic PDFs, runs a deliberately limited ruled-table baseline, and
checks real XLSX output with an independent ZIP/XML reader. `production_ready` always remains false; the synthetic gate is
not an authorization to release. No upload route,
cloud execution, browser UI, OCR service or production release is added.

The current remote branch inventory and main source tree contain Excel → PDF,
not PDF → Excel. No existing PDF → Excel implementation was available to audit
on 2026-11-11. This baseline therefore documents unfinished work rather than
claiming to have finished or extended an unavailable converter.

## Run

```sh
python -m pip install -r scripts/pdfexcel-quality/requirements.txt
python -B -m unittest discover -s scripts/pdfexcel-quality -p 'test_*.py' -v
python -B scripts/pdfexcel-quality/evaluate.py --report-only
python -B scripts/pdfexcel-quality/evaluate.py
```

The last command intentionally exits **1** while any frozen case fails. The
report-only switch permits measurement of known gaps; it does not change pass
counts, remove cases, or grant release approval. Temporary PDFs and XLSX bytes
are removed after the run. The JSON output contains only fixed synthetic case
IDs, counts and content-free diagnostic codes. No source filename or cell text
is logged.

Only use this unsandboxed baseline with the generated corpus. It does not have
production CPU, memory, input size, PDF object/decompression, concurrency or
cancellation guards. Do not wire it to an upload handler. Do not evaluate
private user documents in a hosted environment or publish their results.

## Frozen corpus and measured baseline

There are **16 required conversion cases and 3 expected refusals**. A failed
conversion does not become a successful refusal, and a refused file never
inflates the conversion numerator. Current ruled-table baseline:

- 11/16 conversions pass exact cell, page, sheet and merge checks.
- 3/3 expected refusals pass: encrypted, corrupt and empty input.
- 5/16 conversions fail: borderless tables, scanned tables, mixed native/scanned
  documents, rotated pages and unaccounted narrative pages. These are common classes and are release gaps.

Passing cases cover ruled tables, positional empty cells, multiline values,
merged headers, literal identifiers/formula-like text/locale numbers, Chinese,
Japanese, two tables on one page, multipage tables, landscape pages and an
explicitly accounted blank page. Multiple tables and pages have different
contents and shapes so duplicated-source results cannot pass as preserved data. Source strings must stay literal. Repeated
headers are retained; tables are not silently concatenated. The workbook has
one sheet per table and a page-to-sheet mapping in the result report.

This small synthetic corpus is a **floor**, not a statistically representative
sample of PDF usage. 11/16 does not mean 69% real-world coverage. Even passing
all cases does not establish general production readiness.

## Required result contract

`verify_result(expected, report, workbook_bytes)` compares a frozen oracle to
actual output. The oracle explicitly specifies each page disposition rather than assuming
that every page without a table is blank. The report must enumerate every page,
in order, with an explicit status and exact table-to-page mapping. A mixed file with one converted page and
one OCR/unsupported page fails whole-document acceptance, even if a workbook was
created for the first page. The evaluation adapter may return partial bytes
only to demonstrate this failure; a future product must withhold the final
success state or obtain an explicit reviewed partial-export decision.

The validator checks missing/extra sheets, missing/shifted/extra nonblank cells,
Unicode and newline preservation, merge ranges, literal string types, visible
rows/columns/sheets, duplicate parts/cells/relationships and bounded OOXML
package expansion. It validates required content types, root/workbook
relationships and referenced style indices. It rejects zero-height/zero-width
content and suppressive number formats. It rejects formulas, external links, macro/embedded binary
parts, unsafe paths and XML entity declarations. Expected data is constructed
by the fixture generator, never by the extraction engine under evaluation.
This is not a full OOXML schema or visual-fidelity validator: arbitrary font
colors, clipping, application-specific rendering and all possible style
combinations still require independent application/visual checks.

The adapter is intentionally not configured with text-based table inference.
That heuristic can turn prose columns into false tables; adding it needs a
separate negative corpus and exact structural evidence, not a fallback that
changes the definition of success. OCR likewise requires measured text and
structure accuracy across language, resolution, skew and background noise.

## Remaining release requirements

- Locate or implement the actual PDF → Excel feature in its own reviewed scope.
- Add a larger frozen licensed/synthetic corpus: partial borders, merged body
  cells, footnotes, captions, sparse/wide tables, multiple columns, mixed page
  sizes, multi-page continuations, hidden/OCR text, fillable forms, skewed scans,
  low-resolution photos and common financial layouts. Include negative prose
  cases and quantify wrong-table detection, omissions and cell shifts.
- Define numeric/date conversion as an explicit locale choice with reversible
  preview. Never silently coerce account-like identifiers, leading zeros,
  precision beyond Excel's numeric capacity or formula-looking source text.
- Audit privacy, upload consent, sandboxing, resource limits, authentication,
  deletion, cancellation and all success/failure transitions.
- Independently inspect saved workbooks in Excel or LibreOffice, check complete
  UX against competitors, run all cumulative product regressions and validate
  the supported browsers and physical mobile devices.
- Require successful exact-commit CI and explicit authorization before merging
  or deploying. This change neither merges nor deploys anything.
