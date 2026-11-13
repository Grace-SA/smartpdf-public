# Native rotated PDF table review

## Scope and result

This candidate adds a source-preserving path for native PDF pages whose `/Rotate`
metadata makes horizontal text sideways. It works in a temporary copy only.
All visible nonblank glyphs must become horizontal; the complete glyph multiset
must remain identical. Image-bearing and mixed-direction pages retain their
existing path. The original crop/media boxes and unselected pages are retained.
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
