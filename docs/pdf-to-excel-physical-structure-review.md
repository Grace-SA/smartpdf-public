# Native physical header levels and local section rows

Baseline engine: `b022f845e1b280ee6f8043fd7361f49a9f75bbae`.

## Source-backed changes

Public ICDAR US-002 exposes two independent structural errors without requiring private samples. Two header regions contain a thin line and the bottom edge of a narrow rectangle less than 1.2 points apart, with identical column spans and endpoints. Treating these as separate physical levels incorrectly blocks recovery of two-level headers from the model's three rows. Separately, one section heading and its following numeric record share a model row despite two distinct native baselines.

The header change is confined to complete-word recovery with a proven line/rectangle duplicate, no glyph overlapping the inter-edge strip, one physical internal level, three model header rows, and a unique first-column stub. Prior uncompressed paths retain their former ownership rules. The compressed path permits complete source words evidenced by a model header spanning the same column; it keeps character accounting, non-overlap and physical-line checks. Body cells are preserved apart from the common row-index shift. New duplicate-rule analysis has its own work budget.

Local section splitting requires at least two independently separated sections in the same table corroborating font, size, left boundary, indentation and vertical rhythm. Candidate numeric cells must all occupy the lower baseline. The upper line must contain only the source heading, and neighbouring complete numeric rows must support the spacing. No values or headings are guessed. Rotated, cropped, merged-crossing, closed-grid or ambiguous records remain unchanged. Source literal characters are conserved, and insertion is processed in descending row order.

## Review findings addressed

Independent review reproduced a false evidence case: model cells could omit numeric values from both purported reference headings, making ordinary data rows appear to be isolated sections. A reference cannot qualify merely because its model row contains one nonempty cell. Source glyph coverage must prove the entire heading band is otherwise empty. The same protection covers shifted or superscript content on the candidate heading line.

The review also required bounding new rule processing and rejecting inconsistent or duplicate model-cell metadata rather than choosing an arbitrary cell.

## Validation

- Frozen-code cumulative regression: **292 tests, 291 passed, 1 skipped**, 87.611 seconds. The skip requires the external Stirling integration. New coverage comprises seven physical-header tests and eleven local-section tests, including independently reproduced false-evidence cases. New files pass full Ruff; modified legacy modules pass critical checks, and the diff whitespace check passes.
- Both identical public cohorts export **12/12 files**. Across the same **2,548 annotated nonempty cells**, exact text at position improves **2,271 → 2,500**, whitespace-normalized text at position **2,317 → 2,546**, and normalized text plus span at position **2,315 → 2,545**. Row-aligned normalized text plus span improves **2,528 → 2,545**. Matched annotated merged cells improve **31 → 36 of 38**. There are **no strict or aligned regressions**. All gains are in US-002; no other file changes its cell values/types or merged ranges.
- Artifact checks verify identical table/sheet counts, preserved comments and non-whitespace character multisets for all twelve files. Every US-002 body numeric record is identical and in the same order. Page 1 has 33 → 32 rows after header reconciliation; page 3 has 32 → 32 rows because one header row is removed and the missing section row is restored. Final engine hashes match the benchmark record.
- Both final US-002 worksheets were reopened and rendered with LibreOfficeDev 26.8. The corrected grouped headings, separate range labels and restored section row are visible and readable; no new clipping was observed. Column widths are not a claim of pixel-identical source layout. This does not constitute Microsoft Excel/device acceptance.
- Strict v3 scoring verifies actual source/label/output bytes; the comparison binds its benchmark and scoring reports. Optional historical table-count reference checks remain explicitly **not verified**. The aggregate comparison hash below identifies local evidence, not a published source/output dataset. Repository guard reports the same 129 approved assets absent from the sparse local index; no remote assets are removed.

This document is not a release certification. The fixed 12-file corpus is neither representative of all PDFs nor an established held-out model test set. CI, broader scan/language coverage and Microsoft Excel/device acceptance remain separate requirements. No merge or deployment is performed.

Comparison JSON SHA-256: `f3c05e94704a92bd7c637439757e896944fb47c4eda016ba8c05795e326983ba`.
