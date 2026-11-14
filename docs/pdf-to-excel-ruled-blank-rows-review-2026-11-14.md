# Ruled empty-row integrity review, 2026-11-14

Base: `dc25bfd6dce2c48c8cf2b7fd57a13d0573edb18d`.

## Actual defect

A synthetic native PDF has a four-row physically ruled table: header, record A, an empty record row, record B. The existing `table_from_pdf` removed the empty row and renumbered later rows. Actual conversion therefore reported three rows and placed record B's amount in B3 instead of B4. This was not just a display-height issue: both preview and XLSX data coordinates changed.

The physical-grid adapter now retains its detected row boundaries and empty cells. Its remaining callers are ruled-table extraction and physical card grids, not the borderless text-row detector. The latter remains unchanged; this patch does not invent rows from ordinary paragraph spacing. Card recovery still requires populated cells. Existing table-size, minimum-content and overlapping-cell checks remain unchanged.

## Validation

- Seven new test methods pass using generated original PDFs and unmocked native conversion. They cover interior, leading, trailing and consecutive empty rows; both table/single-sheet layouts; row geometry/closed-grid invariants; a vertical merge across an empty row; an unruled-whitespace counterexample; and continued rejection of an entirely empty grid.
- Independent output checks reopen XLSX with openpyxl and inspect ZIP/XML cell references: the later amount remains B4, B3 stays empty, and preview row count is four. Leading-zero values remain strings.
- Independent code review found no blocking issue, checked the physical-grid/card/blank-merge callers, and requested the added merged-row regression.
- Compileall passed. The final cumulative attempt ran **347 tests**, with **14 environment errors and 1 external-service skip**. This is not a passing full suite. Missing reviewed CJK font, cv2, Docling and OCR dependencies prevent complete validation; a class-level font setup error also prevents its conversion tests from running.
- A same-environment baseline comparison produced exactly the same 14 error identifiers. The unpatched baseline additionally failed four newly introduced row-integrity assertions; the patched version has zero assertion failures. Environment errors were not converted into skips or hidden.
- The unmodified repository asset/privacy guard was run. Its only failures are 129 reviewed binary assets absent from the partial local index; no guard is weakened. Only this aggregate report, the narrow code change and synthetic fixture-generating tests are committed, preserving all unrelated GitHub tree entries.

## Limits

This fixes row loss in native physical-grid reconstruction, not OCR/model row accuracy or universal PDF-to-Excel fidelity. Model/OCR paths, real Excel rendering, full repository frontend/build/browser checks, complete asset checkout and exact-commit CI remain unverified here. No merge, deployment or general production-readiness claim.
