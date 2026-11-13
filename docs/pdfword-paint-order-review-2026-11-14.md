# Word paint-order review, 2026-11-14

Base: `0034ed8ba63cd178f25da255cc62b56ec2f30c06`.

## Reproduced issue and correction

An original synthetic PDF paints `Amount 123.45`, then paints a narrow white rectangle over part of the amount. The source pixels differ, but native extraction previously exported the complete underlying amount with no warning. The narrow rectangle was not retained as a graphic. This is a fidelity problem and can expose text that was visually covered.

The native preflight now observes top-level paint order. A later filled path or image whose bounds intersect earlier visible text takes the existing OCR route. Without a configured OCR worker it refuses without producing a DOCX. It never guesses the covered value or discards the graphic to keep conversion successful. Background graphics before text and nonoverlapping graphics remain eligible for native reconstruction. Unfilled table borders do not trigger this guard. Pairwise checks are limited to 100,000 per page; exceeding the budget also requires OCR.

## Review and evidence

- Independent review requested image-specific coverage; added opaque-image overlap, background-order and disjoint counterexamples before committing.
- Nine new test methods cover partial/full coverage, source-pixel change, background and line counterexamples, image order, bounded work, refusal without OCR, and adapter result/warning export.
- Cumulative Python suite: **129 tests run, 126 passed, 3 skipped**. The skips require the separate OCR preprocessing environment. Compileall passed.
- Controlled adapter output is independently reopened with python-docx; this demonstrates routing and output provenance, not real recognition accuracy.
- The unmodified repository guard ran against the partial checkout. Its only failures were **129 reviewed binary assets absent from the local index**. No guard was weakened. The GitHub tree is based on the original tree, with unrelated paths preserved. No PDF, image, DOCX, private data or model output is committed.

## Limits

This is a narrow top-level paint-order safety improvement, not complete redaction detection. Nested Form XObjects, stroked occluders, blending and other complex painting remain unresolved. Bounds can conservatively require OCR for transparent, clipped or nonrectangular graphics even when visible glyph pixels are unaffected. Approved OCR models are not available here; real OCR results and accuracy were not measured. Full repository frontend/build/browser checks, actual Word rendering, representative document acceptance, full-checkout asset guard and exact-commit CI remain unverified. No merge, deployment or production-readiness claim.
