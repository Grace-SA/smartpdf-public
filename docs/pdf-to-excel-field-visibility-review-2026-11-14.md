# Narrow uniform-field visibility refusal

## Scope and motivation

Feature branch only, based on `d058d786e211ea47dd2dc0363c5a8fe54a86fc83`. No merge/deployment or newly admitted rotation path. This adds a narrowly scoped refusal detector; it is **not a complete field-visibility certificate or comprehensive protection against concealed PDF content**.

Rotation research demonstrated why matching page pixels before/after normalization is insufficient: synthetic image-bearing PDFs with a covered or clipped `888` had identical original/normalized renders, but the downstream native table conversion exported `888` despite its absence from the displayed cell. The original rotated file remained refused. That rotation expansion is still disabled.

This change targets source-matched numeric fields whose complete padded source-glyph region is spatially uniform in the final RGB render at both 144 and 216 dpi. It rejects the conversion rather than rewriting values or publishing an uncertain workbook. The error says visibility could not be verified; it does not claim the source value was proven wrong.

## Conservative eligible subset

- Native, non-OCR tables only; no change to existing OCR routing or rotation handling.
- Two to thirty characters matching the narrow numeric-string syntax. Single-digit fields are outside this detector's current scope.
- Zero-origin, unrotated full-media pages with crop equal to media and normal user units.
- Unembedded, unmodified Latin Type1 faces from the standard PDF font set (12 Helvetica/Times/Courier faces). No custom widths, descriptors, ToUnicode, Type3, unsupported encodings or unknown fonts. Any unsupported font resource declines this detector for that page.
- Font and Form resource metadata traversal is bounded; Forms are not flattened or rewritten. Known inherited resources are inspected without executing external actions.
- Explicitly black source glyphs, upright axis-aligned matrices, glyph height 6–36 pt and width at least 1 pt. Colored/near-white source text is outside scope to avoid treating 8-bit color quantization as proof of invisibility.
- Exact source text match, unique model-cell ownership and no overlapping distinct source glyph boxes. Exact coincident copies may support refusal only; no duplicate text is recovered or deleted.
- The complete glyph union plus half a glyph-height and one point of margin must remain within the view and touch no neighbouring source text. Native ruled tables may use `sourceTextBox` only when `sourceFont=True`; this fallback still rechecks text and ownership and never mutates the input model.
- Strict equality of all final **RGB** pixels, not a grayscale or approximate contrast threshold, at two resolutions. Visible annotations are included by the renderer.

Raw characters/cells, font/resource graphs, image dimensions, comparison work and predicted/actual render dimensions are capped. Both returned RGB bitmaps must match the expected dimensions and each be at most 20 million pixels. Declining an optional check is not a declaration that a field is safe.

## What remains unsupported

Nonuniform covers, partial occlusion, residual noise, unrelated graphic/text ink inside the region, unsupported font resources, ambiguous geometry, single-digit values and native page-context comments are not comprehensively validated by this change. A deliberately noisy cover is an explicit negative test: the detector does not certify or recover its contents. Black source color also does not establish the final effective color after opacity/blending.

Consequently, this detector does not authorize the EU015 rotation extension, remove existing refusals, or establish general production readiness. A broader new-conversion admission path still needs complete final-field visibility and record-association proof.

## Review and tests

Independent review verified the final seven focused tests and two real-model integration tests, including the source-typography fallback. Incorrect text, competing ownership and absent source evidence do not qualify the fallback. It operates on a local model copy.

Generated PDF cases cover white/black/colored covers, clipping, transparent black text, hidden text in Forms, normal repeated overprinting, visible Form text, colored text, extremely faint near-white text, outline text, visible scan images, visible annotation appearances, neighbouring text, tiny/compressed glyphs, untrusted custom font widths, and abnormal returned render dimensions. Visible/nonuniform cases are not certified; they simply do not trigger this narrow detector.

The two end-to-end model tests confirm that ordinary upright PDFs with covered/clipped native numbers fail with the explicit conversion error. The covered case leaves a pre-existing output byte-for-byte unchanged; the clipped case creates no output. Inputs are unchanged. Refusal occurs before the existing atomic workbook writer is called.

Frozen cumulative suite: 541 tests, 540 passed and one external Stirling-service test skipped (110.987 seconds). The focused seven tests plus two integration tests also passed independently.

Frozen 66-file public regression: 59 exports and seven refusals, with every per-file status unchanged from the previous header-fix baseline. All 59 exported workbooks retain identical cell values, types, number formats, comments and resolved semantic styles; all merge sets are identical. One row height in `chart-final__icdar__us-002` differs by 0.0000305175781321 pt (17.61111925781253 versus 17.61114977539066); all other dimensions match exactly. This tiny difference is recorded, not claimed as exact geometric equality. Every recorded engine SHA-256 matches the frozen tested source.

The independent eight-file reference subset remains at 348 aligned normalized text/span matches out of 592 annotated nonempty cells across 17 tables. The refused EU015 contributes 234 annotated cells. Successful export is not a correctness or general readiness claim.

The repository checker remains blocked by 128 approved assets absent from this partial local checkout index. All 128 were verified present in the complete remote base tree; publication preserves that tree and changes only the six reviewed text files. This is not reported as a repository-check pass.

## Delivery constraints

Only reviewed source, generated-fixture test code and this report are published. No source PDFs, private documents, rendered pages or dependency binaries enter Git. No production release is authorized. Exact-commit CI must be checked after push; a failed/unstarted run is not a pass.
