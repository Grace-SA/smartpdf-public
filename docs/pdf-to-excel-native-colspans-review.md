# Preserve source-proven full-width section cells

Baseline: `6d9c6ea9dbca2ba9da6a5ed644547a751e20e011`.

## Restricted recovery

US-007 page 2 includes three physically closed full-width section cells that the layout model reports as first-column cells. A fourth heading has an open right border and must remain unchanged. The new helper changes only column-span metadata and removes covered empty model slots. It does not rewrite the label, invent values or relax the general grid recovery.

Recovery requires a complete source rectangle spanning both the physical table's outer bounds and independently established extents of all model columns. Every column needs at least three distinct populated native body-cell rectangles, with consistent contiguous boundaries. Exact native glyph/word agreement, empty covered slots, complete four-edge coverage and no interior vertical rule are required. Images, annotations, clipped cells, inconsistent metadata and ambiguous source/model ownership decline unchanged.

Candidates are selected before parsing source geometry. Edge count, clustered line-intersection work, physical-cell count and mapping work have explicit limits. Optional geometry failures cannot partially mutate the original model. Native text-layer evidence does not prove visibility under arbitrary transparency, clipping or vector occlusion.

## Independent review

Review reproduced an unsafe partial-column merge when text-start anchors alone made a rectangle look full-width. The helper now proves physical column extents and table bounds independently. A two-point empty edge column could also disappear under the source finder's snapping; the interior-line guard now protects it. Repeated model boxes cannot count as independent body evidence. These failures have rejection regressions.

The pipeline order is native row spans, native column spans, wrapped stub labels, then native header ordering. Wrapped-stub recovery requires exactly three model rows whereas the new helper requires at least five, so those two corrections cannot compete on the same table.

## External-route test audit

The previous test named as a Stirling integration actually allowed metadata rotation to be handled locally. It passed even when the configured service did not exist. The replacement separates an unconditional native test that forbids calling Stirling from a conditional test that invokes the real external adapter directly and forbids local rotation normalization. An invalid endpoint fails the external test rather than passing via a different route.

A temporary loopback-only official Stirling 3.2.2 service with verified official Java 25 binaries passed the direct rotated synthetic test. It was stopped after testing. This is not deployment or a blanket external quality claim: broader real endpoint probes exposed number-format and mixed-direction header defects that are recorded for a separate correction. The bounded local test supervisor also does not establish production backend cancellation or retention guarantees; an HTTP timeout alone is not evidence that the remote conversion job stopped.

## Validation status

Candidate offline-model suite: 330 tests, 329 passed, one genuine external test skipped, 89.360 seconds. The separately executed real external test passed. Ten new source-span tests and Ruff checks pass. Both fixed annotated cohorts have rerun: 22/22 files, 70 pages. The original twelve-file cohort is unchanged. In the second ten-file cohort, normalized text stays 934/951 at position and 949/951 aligned; text-and-span improves 930→933 at position and 945→948 aligned. Correct merged cells improve 16→19/20. Direct workbook inspection confirms only three new merged ranges on US-007 page 2, with identical values, word tokens, row/column counts and source-context comments throughout all 22 outputs. LibreOfficeDev 26.8 reopened and rendered the affected sheet; all three closed section labels are legible and the open-border fourth label remains unmerged. This is not Microsoft Excel/device acceptance. Source gray fills conveying statistical significance are still not fully preserved, and remain a known semantic-style limitation.

The separate unannotated 46-file public robustness baseline completed with 42 conversions and four refusals (mixed directions without the external service, empty file, encrypted file, page-number-only file). SHA-256 checks find no source overlap with the 22 annotated files, but neither selection is population-representative and model-training overlap is unknown. The baseline emitted 67 table worksheets; only WEB-024 used OCR. WEB-014 reports 13 pages without table output. All thirteen were rendered and visually reviewed: pages 1, 6–9, 14–16 and 21–23 contain two-column prose, clauses and lists; pages 10 and 17 contain curves/plots and prose. No missed target table was observed on those pages. This restricted review does not validate the other extracted tables or whole-document content. Therefore 42 conversions is not a full-page preservation rate or broad scanned-PDF coverage. The frozen 46-file candidate also completed with 42 conversions and the same four refusals, with no new errors or timeouts. All successful workbook values, token multisets, merged ranges, dimensions and source-context comments are unchanged. All three candidate runs have identical engine fingerprints and match the final on-disk engine. No accuracy claim is inferred from the unannotated cases.

Repository guard remains blocked only by the same 129 approved binary assets absent from this sparse local index. Remote assets must be preserved through the base Git tree. No merge, deployment or general-production certification is implied.

Comparison SHA-256 values:
- excel-icdar-colspans/comparison.json: `90063ec3704fecbff3d3a008df16afddd6f78907cf283f9104bde5640c9378ff`.
- excel-icdar-next-colspans/comparison.json: `30c968b749cdd4df3a03ad890ec73546e346f3389b6aede1f334966e71aa2e57`.
- excel-web46-colspans/direct-comparison.json: `c9952d4ed4f609e848b4f3639e9b6152bfe5e4e472d0da41340fab4c757d3600`.
