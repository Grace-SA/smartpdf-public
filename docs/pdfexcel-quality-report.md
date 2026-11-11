# PDF to Excel quality audit, 2026-11-11

Status: **Testing (evaluation only); general release blocked**.

The user confirmed Excel was probably unfinished and requested a reviewer role,
common-file coverage, repairs and GitHub submission only. No merge, deployment,
production configuration or public UI change is included.

## What was actually available

The inspected `main` commit is `8f2e8bb30a0cdfa8fa5b59a2c2826efb2122ce32`.
All visible remote branches and the recursive main tree were checked. Existing
Excel code is Excel → PDF. No PDF → Excel implementation branch was found.
This is a new isolated evaluation baseline, not an audit claim about unseen
local work and not the finished converter.

## Research and product quality decisions

- [Adobe's Excel conversion documentation](https://helpx.adobe.com/acrobat/desktop/save-export-documents/convert-to-other-formats/pdf-to-excel.html)
  exposes sheet organization, locale separators and text recognition. These
  inform the necessary product choices; no hands-on competitor acceptance was
  performed and feature parity is not claimed.
- [pdfplumber's primary documentation](https://github.com/jsvine/pdfplumber)
  describes machine-generated PDF extraction and configurable line/text table
  strategies. Its MIT-licensed ruled-table path is used only as a measurable
  local baseline. It is not an OCR implementation.
- [Camelot's API documentation](https://camelot-py.readthedocs.io/en/stable/api.html)
  describes several table parsers and structural confidence signals. Parser
  confidence is not a substitute for ground-truth cell and omission checks.
  Camelot and learned/OCR backends were not benchmarked or adopted here.
- [openpyxl documentation](https://openpyxl.readthedocs.io/en/stable/tutorial.html)
  informs workbook writing. The correctness oracle uses separate standard-library
  ZIP/XML parsing, rather than asking the writer to validate its own cells.

The proposed correctness promise is editable table data with exact literal
values, empty-cell positions, Unicode, line breaks, merged headers and source
page mapping. Identifiers, long integers, locale values and formula-looking
text stay strings by default. Page/table omissions must fail acceptance rather
than produce a misleading successful download. OCR, borderless inference,
rotation, narrative-page handling and partial-export UX remain open work.

## Frozen evaluation and results

The original synthetic generator defines 19 fixed case identities: 16 required
conversions plus 3 expected refusals. Multiple tables/pages use different data
and dimensions to detect accidental duplication. No private source files,
filenames, extracted content, rendered images, inventories or generated binary
fixtures are committed.

The current transparent ruled-table candidate passes **11/16 conversions** and
**3/3 expected refusals**. It fails these common classes:

1. Borderless tables.
2. Scanned tables.
3. Mixed native-text and scanned pages.
4. Rotated pages.
5. Non-tabular narrative pages requiring explicit content disposition.

The default benchmark exits 1 for these gaps. Report-only mode retains every
failure and denominator. `production_ready` is always false. This small
synthetic distribution does not estimate real-world coverage and does not
support a claim that most common PDFs are handled.

## Review and repairs

Author self-review and a separate reviewer found and repaired:

- Empty inline-string cells incorrectly rejected, although the writer uses
  that legal blank encoding.
- Invalid package manifests or root relationships accepted as workbooks.
- Out-of-range style indices accepted even though readers cannot open them.
- Explicitly zero row heights, zero column widths and default hidden rows
  accepted despite invisible data.
- Identical second-table/page fixture values masking duplicated-source loss.
- An empty or altered benchmark inventory producing a false all-green result.
- Inferring blank pages from the absence of an expected table, masking narrative
  content. Expected page dispositions are now explicit and separately tested.
- Report labels implying synthetic success alone could authorize general release.

Tests include formula injection, long/leading-zero identifiers, locale text,
Unicode, multiline cells, merged cells, missing/extra/shifted cells, missing or
duplicated pages, wrong provenance, external relationships, binary embeddings,
DTD/UTF-16 entity handling, ZIP paths/expansion limits, corrupt OOXML and actual
PDF → XLSX extraction against the frozen oracle.

## Verification and limits

The focused Python suite passes 36 tests on Python 3.12. A second review
re-ran the prior failing package/style/visibility/inventory repros and found no
remaining P1 within the explicitly limited evaluation claims. Ruff checks and
format validation pass for all five Python files. Dependencies used for
that evaluation are pinned in the evaluation directory. The expected failing
synthetic gate is verified independently from the passing test harness.

The full repository scanner was attempted and remains blocked by this partial
API-materialized checkout: the existing reviewed binary assets are unavailable
locally. The full inventory and scanner are not weakened or modified. Submission
must preserve the original remote base tree and prove that only the new text
files changed; all existing source and asset blob IDs must remain unchanged.
This exact-diff check is not described as a full scanner pass.

Cumulative product unit/browser regression, publication build, real-device UX,
Excel/LibreOffice visual opening, production sandbox/load testing and exact-
commit successful GitHub CI have not been established by this work. Release
remains blocked. Detailed next steps and commands are in
[`scripts/pdfexcel-quality/README.md`](../scripts/pdfexcel-quality/README.md).
