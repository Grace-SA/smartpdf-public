# Lost source-format semantics: explicit export notice, 2026-11-14

Base: `5bb68f99eca594456416f00ed3466302ff069350`.

## Remaining public discrepancies

The 22-PDF frozen corpus was rechecked at cell level. The normalized-text positional differences are concentrated in US008's unresolved grouped-heading row and US001's last-column header tier. US007 also has one missing section colspan. The latter two source regions have open outer borders, so absence of an internal line alone does not meet the existing closed-cell evidence requirement. Those structural guards were not relaxed to maximize a score.

A separate, higher-consequence interpretation risk is visible in US007: its key says gray backgrounds indicate statistically significant favorable effects, with another pattern for unfavorable effects. The exported cells retain numbers such as 0.16 but not the gray backgrounds. The workbook generates its own header colors. A reader could therefore misread missing shading or generated colors as source evidence. This is a semantic presentation limitation that text/span benchmarks do not measure.

## Safe mitigation, not invented formatting

Every conversion result now warns that original colors, shading and patterns are not preserved and that generated workbook colors do not encode the source meaning. The same notice is placed in the first cell comment of every exported table/form so that it travels with the downloaded workbook, including when there is no extracted page context. Existing native/OCR context and its uncertainty label are appended, not overwritten.

The notice is unconditional because native rectangles alone do not establish visible source color under transparency, images, patterns or clipping. This avoids claiming that an unflagged source has no color semantics. No fills are reconstructed, no numeric significance is inferred, and no values or table structure are changed. Users must consult the original PDF and its legend for color-dependent meaning.

## Regression scope and limits

Synthetic tests cover tables with no page context, multiple pages in both separate-sheet and single-sheet layouts, preserved values and exactly one notice per table. Existing context tests now check both the result warning and preserved comments, including crop exclusion and formula-like text. This is an explicit-loss disclosure improvement, not restored shading support or a higher accuracy score. Comments may not be immediately visible in every spreadsheet viewer; the conversion warning is a separate disclosure channel. Full source-format preservation remains unresolved.

Only source, synthetic regression tests and this report are submitted. Public PDFs, annotations, rasters and workbooks are not redistributed. No merge or deployment.

## Validation and independent review

- Independent reviewer passed 6 source-context and 5 scan-context tests, then 9 form-conversion/form-rule tests. The existing single-sheet DrawingML and comment VML relationship/schema checks remain. The review requested retaining a strict drawing-directory total alongside file-type counts; that assertion was added rather than weakening the old guard.
- Initial cumulative testing caught two old assumptions about comment/drawing counts. They were updated to require the new two comments, exactly one original footnote, one form-rule XML and one VML, while rejecting extra drawing files. Production code did not change during these test corrections.
- Both frozen public manifests rerun: all 22 PDFs exported. Counts remain 2547/2548 normalized positional cells on the original set and 934/951 on the next set; merged-cell matches remain 37/38 and 19/20. This is not an accuracy gain.
- US007 before/after workbooks have identical values, dimensions and merges on both sheets. Every existing source comment remains verbatim following the notice.
- Unmodified repository guard remains blocked by 128 existing approved assets missing in this partial checkout. Unchanged remote assets are preserved. Exact-commit CI, actual spreadsheet application rendering and full release acceptance remain unverified.

Local evidence SHA-256 (not redistributed):

- `excel-public-icdar/benchmark.json`: `c06049cf9315c9e147ffc1695be733df681da7f09539d906c7c575220e85e550`
- `excel-public-icdar/cell-evaluation.json`: `d934aba60c7ca4c1a53242e76fca053fa2d8e5af107d3a8f19ece9da3427bf02`
- `excel-public-next/benchmark.json`: `75b4d4e64068822d027ffdc89cf3f3ca147524a84b09e313ada1f8c7438bdc77`
- `excel-public-next/cell-evaluation.json`: `fb965d5a7665014cf7a4dbf1f95a6e6b2fe9f7bdbd98db9c1e2acb1c9e3f07b0`

Final cumulative suite after the review assertion: **411 tests run, 410 passed, 1 external Stirling integration skipped**.
