# Preserve a wrapped label in a closed two-row source grid

Baseline engine: `0e3d7ada437f141d59c67661d545d1e7400a3bb9`.

## Reproduction and restricted change

EU-007 page 2 has a complete closed two-row, seven-column physical grid. Its first body-cell label wraps over two lines; the model instead creates a third logical row for the continuation. Existing general-grid recovery correctly declines a shape mismatch and requires more physical rows. Those broad gates are not relaxed.

The added helper accepts only a complete physical 2×N unmerged grid and a model with exactly three rows, where the sole text in the final row is the first-column continuation. Every other physical cell must map uniquely to one model cell, with complete native glyph and word agreement. The two label fragments must have identical valid font/size, normal neighbouring baselines and aligned left edges. All physical grid borders require independently checked edge coverage, and even a partial interior horizontal line prevents joining. Images, annotations regardless of Contents/AP, viewport clipping, ambiguous ownership, inconsistent metadata and geometry-budget failures retain the previous result.

The final change joins the two existing strings with a newline, removes the redundant model row and adjusts only the combined label bbox. It does not generate values or rewrite the six numeric records. This is text-layer/grid/crop consistency, not a general visibility proof under arbitrary rendering modes, clipping or vector occlusion.

## Review

Independent review found that two invalid but equal font-name values could wrongly satisfy the same-font condition. The helper now requires a nonblank string identity before comparing fonts. None, empty, numeric and whitespace-only font identities have explicit rejection regressions. Other malformed source geometry and annotation/image cases decline safely without partially mutating model data.

## Validation

- Final tested-change-set regression: **319 tests, 318 passed, 1 skipped**, 83.831 seconds. The skip still needs the external Stirling integration. Eight original helper tests and full Ruff on the new files pass; critical legacy integration and whitespace checks pass. Independent review verified the font fix against its failing cases.
- Both frozen public cohorts reran successfully: **22/22 files / 70 pages**, with **no strict or aligned regression**. The original twelve-file cohort is unchanged. The second ten-file cohort improves by one correctly grouped label: normalized text at position **933 → 934 / 951**, normalized text-and-span **929 → 930 / 951**, aligned normalized text **948 → 949 / 951**, and aligned text-and-span **944 → 945 / 951**. Exact text improves **910 → 911 / 951**.
- Direct workbook inspection confirms the only value/row-count change is EU-007 page 2, from 3×7 to 2×7. Its existing two label fragments are joined with a newline; all six numeric values and every header value remain identical. Across all 22 files, word-token multisets, source-context comments and merged ranges are preserved, and every other worksheet value/dimension is unchanged. Both final engine fingerprints match their benchmark records.
- LibreOfficeDev 26.8 reopened and rendered the affected worksheet. The complete two-line label now shares one body row with its six values and is readable without clipping. This remains a smoke check, not Microsoft Excel/device acceptance.
- Repository guard retains the known 129 approved-asset absences in the sparse local index; no remote binary assets are removed. Source PDFs, reference XML and workbooks remain local; optional historical table-count checks remain explicitly unverified. No merge/deployment or claim of broad production certification.

Local comparison SHA-256 values:
- excel-icdar-wrapped: `0ec2d3a9fa97174f8737c2c56875fb23e46700313f30de1f0629dbc3affd8526`.
- excel-icdar-next-wrapped: `7dc7cb05530ba055475125f3417ff4bde229438e3df970766a75617e4f799644`.
