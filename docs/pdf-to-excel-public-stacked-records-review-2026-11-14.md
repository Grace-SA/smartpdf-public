# Public-document stacked-record fallback review, 2026-11-14

Base: `34146e92360872da1815a37c5614d2a65c172860`.

## Independently reproduced defect

The fixed public ICDAR EU008 PDF visually contains 13 separate body records, including one record with two blank amounts. Its source grid rules only the header, large body region and total. Without `PDF_EXCEL_MODELS`, the native fallback treated the physical body as one row: output was 3 x 4 rather than the independently annotated 15 x 4. The body had 13 label lines but numeric stacks of 12, 13 and 12 lines, losing blank-entry alignment. A source-page rendering confirms the separate records and blanks. This is a native-only fallback defect, not a model-enabled benchmark defect.

The native fallback now refuses a ruled row containing at least two distinct, unmerged columns with three or more numeric lines and directs the caller to configure the table recognition models. It does not guess how to split or pair values. Model-enabled extraction continues using its existing structure path; EU008 still produces 15 x 4, and all 58 independently annotated nonempty cells match at their positions after whitespace normalization.

The independent reviewer reproduced the public case and approved the conservative refusal. Four synthetic regression methods cover distinct-column/same-row evidence, two-line and merged-cell exclusions, the deliberately narrow single-stack boundary, actual native refusal, and a late-page failure that preserves an existing output file.

## Public evaluation protocol

The two existing frozen manifests select 22 upstream public PDFs plus independent ICDAR structure XML from the pinned Camelot revision. Files are downloaded with Git-blob verification; corpus, references and output artifacts are SHA-256-bound by the existing scorer. Reference labels never enter the converter. Inputs, annotations, rasters and workbooks remain local and are not redistributed in this commit. The final model-enabled rerun uses unchanged gates and the restored pinned/offline runtime.

This change protects a fallback configuration; it does not claim improved model-enabled corpus scores. US008 still combines two visually distinct group-heading lines, creating row-position differences. Values remain attached to the correct record labels; this is not described as amount corruption. A speculative heading split was not shipped.

## Final local validation

- Python regression: 407 tests run, 406 passed, 1 skipped (external Stirling service not configured). Includes the existing multipage rendered-scan OCR, blank-row and merge regressions; public ICDAR PDFs are not claimed to be a scanned-document population test.
- The production change is restricted to the no-model native fallback. The model-enabled public rerun is a nonregression check, not evidence of better recognition.
- Restored unchanged Python/helper/manifest files were checked against the original Git blob bytes before the final rerun. The 87 locked dependency versions and eight pinned model files were restored without changing dependency declarations or model pins.
- Independent code review and source-page visual review completed; threshold and merged-cell exclusions were added to the regression assertions.
- The unmodified repository check remains blocked by 128 approved assets missing from this partial checkout. No check was weakened. Only the converter, synthetic regression source and this report are included in the commit; the remote base tree preserves the existing assets.

## Frozen public corpus results

| Manifest | Converted | Annotated tables | Nonempty cells | Normalized text at position | Text plus span at position | Row-aligned normalized text | Matched merged cells |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Original 12 | 12/12 | 37 | 2548 | 2547/2548 | 2546/2548 | 2547/2548 | 37/38 |
| Next 10 | 10/10 | 21 | 951 | 934/951 | 933/951 | 949/951 | 19/20 |

Position and row-aligned metrics are intentionally shown separately. Row alignment can conceal missing/grouped headings, so the higher score is not substituted for positional correctness. These are the repository scorer's metrics, not official ICDAR scores or real-world accuracy. The model-enabled counts match the preceding diagnostic run; only native fallback refusal changed.

Local evidence SHA-256 (artifacts are not redistributed):

- `excel-public-icdar/benchmark.json`: `9e723283b1b28f480325eb7f76b512465a5d7ffcc5dcb328a8268e4b40cf46ae`
- `excel-public-icdar/cell-evaluation.json`: `b424c64623e8cda5fdba306e12d637c1d9ee9bd6197c3472a29c86a496ef80da`
- `excel-public-next/benchmark.json`: `759d0cee0745d57b5c13a9994b9458df5ff8d4ca021a75622f49c65b172963d2`
- `excel-public-next/cell-evaluation.json`: `95671ee945e6589c9cf3b38230340feb37ce7e36ccca685bb4d854f3e20a6ea9`

Converter SHA-256: `0c5aec0ac3154fca221eaa97e83dc30b8233435484289614c6646d0ca7f6ac17`.

## Limits

The new predicate does not cover single numeric stacks, mixed numeric/text stacks or merged-body cells. It can conservatively refuse legitimate multiline numeric lists; an unambiguous model-backed structure is required rather than presumed. The fixed corpus is limited and is not a population accuracy estimate. Real OCR accuracy, actual Excel rendering, full frontend/build/browser acceptance, complete assets, real Stirling integration and successful exact-commit CI remain separate release requirements. No merge or deployment.
