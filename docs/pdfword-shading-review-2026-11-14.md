# Gradient paint safety review, 2026-11-14

Base: `92ef84d21ba80698be58fcdf06d3147bed56735b`.

## Reproduction and correction

Original synthetic PDFs paint an axial or radial gradient across amount digits. Before this patch, `FPDF_PAGEOBJ_SHADING` objects did not participate in paint-order checks and the native path exported the entire underlying amount. PDFium raster evidence confirms that the affected region's dark glyph pixels disappear; this is not merely a background-colour change.

Shading objects now enter the same bounded overlap guard as images and paths. Later overlapping gradients require rendered OCR; absent configured OCR, conversion refuses without creating output. Nested Form transforms and nondefault Screen blending are exercised as well. No private or third-party document is needed for this reproduction.

## Evidence and false-positive counterexamples

- Seven new test methods cover axial/radial shading, actual digit pixel loss, background-before-text, explicitly clipped disjoint shading, transformed Forms, Screen blending and no native output without OCR.
- A meaningful conservative false positive is separately documented: PDFium exposes page-wide bounds when only the shading dictionary BBox limits the gradient. A far-away gradient with/without explicit clipping produces exactly the same rendered pixels, but without the explicit clip it can require OCR. No narrower geometry is invented or assumed.
- Independent review passed all 41 combined paint/transparency guard tests with no blocking findings.
- Cumulative Python suite: **161 tests run, 158 passed, 3 skipped** because separate OCR preprocessing dependencies are unavailable. Compileall passed.
- Unmodified repository guard continues to report only 129 missing reviewed binary assets in this partial checkout. Only code, original synthetic fixture-generating tests and this report are committed; unrelated remote tree entries are preserved.

## Limits

This is a deterministic routing/privacy-boundary fix, not real OCR accuracy validation or a universal guarantee that every visually hidden character is detected. Unusual graphics-state combinations, mesh shadings, clipping/soft-mask interactions and broad representative-document coverage still need validation. Complete frontend/build/browser tests, actual Word rendering, full-checkout assets and exact-commit CI remain unverified. No merge, deployment or production-readiness claim.
