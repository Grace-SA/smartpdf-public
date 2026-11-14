# Source section-label line breaks, 2026-11-14

Base commit: `038d96103d7500b7cf1e4570e9d9f0a32c812c59`.

## Evidence and rejected structural repair

The fixed public ICDAR US008 page 3 has two source lines merged by the table model into one section cell. Its table has seven exported rows versus eight reference rows. Inspection of the source page and captured intermediate model confirms that the twelve numeric cells remain with their respective record labels; the defect is not described as misplaced amounts.

The source's apparent indentation is not a proof of separate logical rows. The two lines are approximately centered at 159.1 and 158.5 PDF points, their baseline spacing is ordinary text leading, and there is no separating horizontal rule. A wrapped centered heading or hanging-indent label can satisfy the same typography and spacing; a later similar heading does not remove that ambiguity. The independent reviewer therefore rejected inserting a row from geometry alone. No document names, phrases, annotations, expected dimensions or amounts are used in production logic.

## Safe, deliberately limited improvement

Existing native-header glyph ownership checks now also admit explicitly model-marked section labels. For those labels, source word order must already exactly match model word order. Only source line breaks are recovered; the table dimensions, cell coordinates, spans, source boxes and numeric strings are not moved or reconstructed. The ordinary column-header reordering behavior stays unchanged. Existing image/annotation/overlap, font, matrix, crop, baseline, ASCII and exact-word-multiset restrictions still apply.

This improves readability without claiming to fix the eight-versus-seven-row structural discrepancy. The US008 workbook comparison found exactly one changed value, A2 on page 3, changing a space between the two source lines to a newline. Every other value, sheet dimension and merged range was identical. Native text visibility under arbitrary PDF clipping/occlusion remains outside this helper's guarantees.

## Counterexamples and review

Three new test methods cover centered parent/group labels and ordinary centered wrapped headings without inventing rows, unchanged unrelated numeric data, reversed section-word order refusal, image/annotation ambiguity and ordinary numeric-body exclusion. All 12 focused native-order tests passed. Independent code review approved the narrow change and its non-structural scope.

Public PDFs, annotations, intermediate captures, rasters and workbooks remain local. Only production source, synthetic test source and this report are submitted. No merge or deployment; this is not general release acceptance.

## Final validation

- Full Python suite: 410 tests run, 409 passed and 1 skipped (external Stirling service absent).
- Both frozen public manifests rerun with the pinned offline models: all 22 PDFs exported.
- Original 12: 2547/2548 normalized-position text matches; 2546/2548 text-plus-span; 37/38 merged cells.
- Next 10: 934/951 normalized-position text matches; 933/951 text-plus-span; row-aligned normalized text 949/951; 19/20 merged cells. These counts are unchanged. Readability improved, not the structural score.
- No corpus/reference labels enter the converter. Public samples are not a population or scan-accuracy estimate.
- Unmodified repository guard remains blocked by 128 approved assets absent from the partial checkout. No check is bypassed; unchanged remote assets are preserved by a base-tree commit.
- Exact-commit CI and real Excel/browser release acceptance remain unverified.

Local evidence SHA-256 (not redistributed):

- `excel-public-icdar/benchmark.json`: `03c7dfdab904fd7308b9ada0537d2db0b6fe1cd8d53545936efd9b896e8a061a`
- `excel-public-icdar/cell-evaluation.json`: `e0073d3047a6f78fcc639abbb0e275d64347d449bac6c1eb839f9ffd53d8f811`
- `excel-public-next/benchmark.json`: `7f7a5f4549389c70c5a98a18203b45928110471a36a7eaf878fe5e636266caad`
- `excel-public-next/cell-evaluation.json`: `3bc461c4b3a4ac206362238eb583b04cf5aa7f3d733bec20770c99949f3e8ab2`

Changed helper SHA-256: `ddd0174bdc92e38133392b09b72bc7cd97d590137a016eff8d7f8a741b7d3909`.
