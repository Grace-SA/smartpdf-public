# Native rotated PDF table review

## Scope and result

This candidate adds a source-preserving path for native PDF pages whose `/Rotate`
metadata makes horizontal text sideways. It works in a temporary copy only.
All visible nonblank glyphs must become horizontal; the complete glyph multiset
must remain identical. Image-bearing and mixed-direction pages retain their
existing path. The crop/media boxes rotate together with content when required; their source
view is preserved. Unselected pages are retained.
The existing native/model table extraction pipeline then runs on that copy.
A warning tells the user which pages were reoriented.

The module is included in the benchmark engine fingerprint. No source documents,
model weights, generated PDFs, workbooks or rendered evidence are committed.
No production flag, model configuration or deployment workflow was changed.

## Verification

- Seven new regression tests pass, including 90/180/270-degree conversion with
  and without a crop; exact literal cells preserve leading zeros, locale decimal
  punctuation and negative signs without requiring Stirling.
- Independent PDFium rendering in a common upright orientation gives identical
  pixels for all six rotation/crop combinations. Independent code review also
  checked three nonzero-MediaBox-origin/crop cases with identical pixels.
- Original input hashes, temporary-file cleanup, unselected pages, image/mixed
  direction exclusions, and oversized-page rejection before glyph parsing pass.
- The reviewer identified dimension checks occurring too late; this was fixed
  before delivery and covered by a regression test.
- New files pass Ruff. The final Python discovery run executes 193 tests:
  190 pass and three environment errors remain. The conversion test class cannot
  initialize without the repository CJK font; two other tests cannot import
  Docling. The blocked class's individual tests did not execute. This is not a
  complete suite pass and does not replace the prior configured model tests.

## Remaining acceptance work

The frozen 200-file corpus, private source-review references, Docling models,
Stirling and OCR integration services are not available in this cloud checkout.
Their latest recorded 161/200 output result and 49/59 strict reviewed passes
have **not** been remeasured on this candidate. This change is not evidence that
all previously failing rotated documents now pass.

Full repository validation, browser cumulative regressions, independent workbook
rendering, real devices, production Linux/container capacity and the exact
commit's CI remain unverified. The partial source checkout cannot materialize
all existing binary assets through the connected text-file API. The repository
privacy checker was run without weakening its rules and remains blocked by the
missing assets; unchanged remote asset blobs must remain intact during commit.

General production readiness is still false. There was no merge or deployment.

## Follow-up: real model validation and content-stream rotation

Further work provisioned the pinned CPU Torch/Docling/OCR runtime and downloaded
all model files with the repository's exact revision, byte-count and SHA-256
checks. The missing CJK font was obtained from its official upstream and matched
the existing approved asset hash exactly. No credentials or paid inference were
used. This supersedes the earlier local dependency blockers, not the missing
full-repository/browser/production acceptance.

The native orientation path now also handles unanimous quarter-turn text inside
a rotated page's content stream. It transforms the content and all page boxes
together, verifies unchanged complete glyph content and horizontal output, and
otherwise retains the existing path. Mixed direction, skew and image-bearing
pages are not guessed.

- Final model-enabled Python suite: **224 tests, 223 passed, one existing
  Stirling-dependent integration skipped**. No failing tests. Eight new rotation
  tests pass, including content-stream rotations and crop preservation.
- Independent review exercised nine further nonzero-MediaBox-origin / content
  rotation / metadata rotation combinations; normalized PDFium pixels matched.
- A real [public sideways table](https://raw.githubusercontent.com/camelot-dev/camelot/92777b852e00933a5c4b9ba642601784604356cd/tests/files/clockwise_table_1.pdf)
  previously required Stirling in this environment; the candidate produced a
  13-row, 10-column workbook through the pinned local model. Independent source
  image review checked all 123 nonempty cells and five merges. Values and merges
  match the table. Title, explanatory footnote and page footer are not included:
  this is table-content evidence, not whole-document semantic fidelity.

The original 200-file corpus and its private review ledger have still not been
rerun. Do not combine this pilot with historical coverage scores. No full visual
workbook, device, Linux-container capacity or production acceptance is claimed.

### Frozen 12-file public pilot

A new, separately named pilot freezes the first 12 downloaded public files with
source hashes before running both `cb09ebf` and this candidate in the same pinned
Linux CPU environment, 180 seconds per process, sequential execution. It is not
the original 200-file benchmark.

- Baseline: 10 outputs, two refusals. Candidate: 11 outputs, one refusal.
- All ten shared outputs have identical canonical cell-value and merge hashes.
- The new output is the independently reviewed sideways table above. The other
  rotated input contains mixed text directions and retains its prior refusal.
- No timeouts or unhandled errors. Output success is not overall accuracy.
- Manifest SHA-256: `d35367b5e8a3fcf388b304c1615f593f575cdf0852027456373941479e658aa3`.
- Result SHA-256: `16d790741dc667d00cd7ef8908468c96521269178b149fb8c8b39e0643efd54d`.

The raw public inputs, local inventory, outputs and rendered images remain local.
Only this aggregate evidence and original synthetic test code are committed.
