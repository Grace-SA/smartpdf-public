# Mixed raster/native OCR routing review, 2026-11-13

Base: `fc9fbd9c0778b2f8420663704f0258e52ac4b9b1`.

## Actual environment

`PDFWORD_OCR_PYTHON` and `PDFWORD_MODEL_ROOT` are unset. PaddleOCR/Paddle, Torch and Transformers are unavailable. The approved OCR models are not provisioned. System Tesseract is available for diagnostics only; it is not configured as a SmartPDF engine and was not substituted for the approved runtime. Real production OCR recognition accuracy cannot be verified here.

## Reproduced silent coverage gap

A native title above two separate raster regions, each below 65% of page area, bypassed OCR despite combined coverage above 65%. The result reported success with two images and only the title editable, without an OCR warning.

Reproduced with an explicitly derived fixture: rasterized the already documented public W3C OpenOffice PDF, split it into two raster tiles and added an original native title. Baseline output: **45 text characters, 2 images, no warnings**. Tesseract diagnostic confirmed that the raster contains text; this is not an OCR accuracy measurement or an untouched real-document benchmark. The corrected path refuses without a configured OCR worker and does not create output. A controlled adapter test verifies that configured OCR is called and its recognition warning retained.

Coverage now uses the union of all raster-region rectangles, clipped to visible page bounds, rather than the largest individual region. Overlap does not count twice. Geometry work is capped at 512 regions; larger counts use the guarded OCR path. Existing single-large-region and purely scanned-page behavior remain guarded.

Independent review found an off-page clipping overcount in the first implementation. All four coordinates are now clamped and empty rectangles discarded; symmetric off-page regression tests added before publication.

## Validation and limits

- **120 Python tests passed, zero skipped**; six new mixed-raster methods cover fail-closed output, adapter invocation/warnings, collective coverage, overlap/small images, bounded geometry and off-page rectangles.
- Compileall passed. Existing public Word/OpenOffice double-column, W3C table, five-page numbering and federal statistical table samples still parse with unchanged page counts and no new warnings.
- No claim of production OCR success: only deterministic routing and output-failure behavior were tested. Native and simulated OCR tests are not recognition benchmarks.
- Raster content below the collective threshold, photographs/charts, clipped/hidden native content and complex scan structure still need broader real-model validation. This heuristic does not classify every image as text.
- Unmodified repository guard still reports 129 absent reviewed assets in this partial checkout. No public/private PDF, derivative, generated DOCX or raster is committed.

Complete OCR provisioning, representative scanning corpus, actual Word, full-checkout guard and exact-commit CI remain substantial release blockers. No merge or deployment.
