# Scanned table context preservation review

Follow-up to `26ac16559b7d4d9f33259d142a0b79bccbff7f82`.

## Bounded change

The complete-ruled-grid scan path now reuses its existing RapidOCR results to preserve text wholly outside all detected table rectangles as a page-level Excel comment. No second OCR request, model or remote service is added. The comment explicitly says **OCR text (uncorrected; verify against the scan)**. This is not a claim of exact OCR or a footnote-to-cell association. Native context behavior remains unchanged.

Context is omitted, not guessed, when outside-table text is below 0.85 confidence, confidence is invalid, its polygon is skewed or non-horizontal, its structure is malformed, or the bounded text/XML limits are exceeded. Table-overlapping and outside-raster regions are excluded. Context omission does not reject an otherwise usable table. Coordinates come from the same cropped raster used by the existing table detector.

The independent review found nonfinite/out-of-range/non-numeric confidence handling could break this optional path. The final validator accepts only finite confidence in [0.85,1] and safely rejects malformed OCR evidence. Five new tests include real OCR, uncertainty/skew/illegal XML, malformed score/line data, table-overlap and out-of-image boundaries, literal non-formula text, and multi-table exclusion.

## Evidence

- Final pinned-model cumulative result: **236 tests, 235 passed, 1 skipped**, 83.945 seconds. The skip remains the external Stirling integration without `STIRLING_URL`.
- Independent real cropped-scan verification in both table and single-sheet layouts: adding context leaves cell positions, types, values and merges unchanged; hidden cropped text is not included.
- Public Camelot WEB-024 (`tests/files/image.pdf` at the pinned commit documented in the rotation report) remains successful with identical cells/merges. It does not gain a context comment; this is a negative coverage result, not a new success.
- A local 144-dpi rasterization of normalized public WEB-009 (not an independently captured real scan) succeeds before and after, with identical cells/merges. The new output preserves OCR title, note and footer in a comment. Raw note is `*Data notavailable`, not the original spacing.
- Comparison against the native WEB-009 workbook exposes a remaining OCR gap: both have 13 rows, 10 columns and 123 nonempty cells, but only 116 corresponding strings exactly match. Three strings lose spaces; four asterisks are recognized as stars. These are pre-existing recognition errors and are **not** silently rewritten. This single synthetic raster comparison is not an overall accuracy estimate.
- New helper/tests pass Ruff; changed Python modules compile. Repository guard is run, but the sparse source index still lacks 129 approved assets. Only reviewed text changes are applied to the remote base tree; missing local binaries are not deleted remotely.

## Remaining gates

This improves retention, not OCR accuracy. Borderless/model-structured scanned context, low-confidence notes, rotated annotations, reliable punctuation and spacing, representative real scan acceptance and production runtime/browser/device validation remain open. Comments must be opened to read them and are not visual page reconstruction. No private samples or public input PDFs/rasters are committed. No merge/deploy, and no CI success claimed while the account has no Actions quota.
