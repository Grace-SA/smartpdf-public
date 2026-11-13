# Complex stroke rendering review, 2026-11-14

Base: `387e4d94f9521863c8eca97cb3b427e802487bdf`.

## Reproduced defect

Original synthetic PDFs draw an amount and then a narrow white cubic curve or multi-segment polyline across part of its digits. PDFium rendering confirms changed glyph pixels. The previous guard handled a single straight stroked line only, so native conversion still exported the complete underlying amount. The narrow vector region was not retained as a visible image.

All stroked paths now participate in bounded paint-order overlap checks. An overlapping path requires rendered OCR rather than trusting underlying text. To avoid falsely treating the empty middle of a simple table-border rectangle as painted content, only an exact five-segment, unfilled, axis-aligned rectangular outline can supply a clear interior. Its interior is conservatively inset by a full transformed stroke width. Curves, compound/nonrectangular paths, fills, unknown drawing states and zero-width outlines have no such exemption. This does not relax any previously guarded filled/text-transparency case.

## Adversarial validation

- Eight new test methods cover cubic and polyline occluders, background/disjoint counterexamples, thin versus thick rectangular strokes, filled rectangles, ancestor transformations, clipping, Screen blending and no output without configured OCR.
- True source raster changes are checked for the curve/polyline examples. A separate clipped-out stroke produces unchanged pixels but still requires OCR conservatively; this is explicitly not counted as a proven visual occlusion.
- Independent review passed all 34 combined guard tests and checked that an early-closing malformed contour receives no clear-interior exemption.
- Cumulative Python suite: **154 tests run, 151 passed, 3 skipped** because OCR preprocessing dependencies are unavailable. Compileall passed.
- Unmodified repository guard still reports only 129 missing reviewed assets in the partial local index. Only source, synthetic fixture-generating tests and this report are committed; unrelated GitHub entries remain unchanged.

## Limits

Bounding-box overlap intentionally trades some native-conversion coverage for safety. It is not a complete pixel-level visibility proof, nor a guarantee of OCR accuracy or perfect redaction detection. Shading objects, unusual graphics state combinations and broad representative-document acceptance remain future work. Actual Word, complete frontend/build/browser tests, full-checkout assets and exact-commit CI are not verified. No merge, deployment or production-readiness claim.
