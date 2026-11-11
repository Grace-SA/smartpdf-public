# PDF to Word quality gate

Status: proposed engineering acceptance standard, not a claim of release readiness.
The 2026-11-11 follow-up asks for conversion suitable for the great majority of
common files, with review findings fixed and source submitted to GitHub only.
No merge or production deployment is included.

## Measure usefulness separately from safe refusal

Keep the original 17-case support/refusal matrix and identities. Add new cases;
never replace a difficult input with an easier one or count an expected refusal
as a successful conversion. Report at least these separate totals:

- Converted and independently verified, by document category.
- Refused safely, including unsupported and malformed inputs.
- Accepted with missing, duplicated, reordered or changed content.
- Failed, timed out or not tested, with the exact candidate revision.

A 17/17 expected-outcome result is a safety/regression result, not 100% useful
conversion coverage. The current simple-native-text worker does not meet the
broader target. Geometry heuristics cannot prove that arbitrary text is prose.
Small-gap tables and semantic reading-order ambiguity remain unresolved.

## Required common-document coverage

Maintain a fixed, provenance-reviewed corpus with independent expected outputs
for plain letters, mixed-font prose, Chinese/English and mixed-script text,
headings and lists, invoices and statements, bordered and borderless tables,
multiple columns, headers/footers, links/footnotes, diagrams/images, scanned
pages, and mixed native/scanned documents. Include multiple source applications,
page sizes, crops, rotations and font encodings. Publish only original synthetic
fixtures or material specifically licensed for redistribution; private validation
stays local and contributes only aggregate results.

Before describing the product as general-purpose, freeze representative category
weights and a held-out corpus, then achieve at least 95% independently verified
useful conversion overall and at least 90% in each supported common category.
Unsupported common files count against coverage. These are proposed minimum
engineering gates; a small hand-picked synthetic suite cannot establish them.

## Correctness gates

- Zero known accepted-output content corruption. Numbers, decimal separators,
  signs, dates, identifiers, visible text and reading order must match independent
  source expectations. Do not remove all whitespace when comparing: it can hide
  changed amounts, merged words or lost table boundaries.
- Paragraph/list/table boundaries and page/section geometry must be checked
  separately from text. A screenshot-only Word file is not editable conversion.
- Reopen generated DOCX with an independent OPC/XML reader and actual Microsoft
  Word; edit and save representative English and Chinese examples. Render and
  inspect every page of fixed acceptance cases. Parser success alone is not a
  layout or editability pass.
- A late unsupported page must reject the whole job without a partial download.
  Preserve original files, source order and fixed page markers through the
  1-page and 200-page boundaries. Distinct markers must prove order, not just
  that the same phrase appears 200 times.
- OCR, tables, multi-column and graphic reconstruction require their own quality
  gates and reviewed runtime/licensing choices. Keep their current refusals until
  a tested implementation exists; do not broaden claims by weakening validation.

## Runtime and delivery gates

Pass the exact candidate's cumulative unit/integration, browser, publication-scope
and independent existing-tool checks, plus repository privacy/asset validation.
Repeat real isolated-container tests for startup, conversion, cancellation,
timeout, uncertain creation and deletion. Failure to prove cleanup must close
service admission. No new network access, document retention, paid dependency,
unsafe fallback or private upload is implied by this quality work.

Record whether each check passed, failed or did not run. Old green results do not
cover new code. An account-gated CI failure is still not a passing run. Keep the
PR in draft while required checks or general-coverage gates remain unmet.
