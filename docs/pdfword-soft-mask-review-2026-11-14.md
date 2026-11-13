# Text soft-mask safety review, 2026-11-14

Base: `b84ed0199c5d8cd147cde84c6a198b12a73c3f2a`.

## Reproduced disclosure boundary

An original synthetic PDF uses a luminosity soft mask to hide `Amount 123.45` while retaining a visible heading. Before this patch, native conversion exported both strings without warning. The PDFium page-level transparency flag is false in this fixture, but the masked text object's transparency flag is true. Testing only fill alpha or page transparency is insufficient.

The preflight now checks object-level transparency on both text objects and Form XObjects. Soft masks or nondefault blending on the text or its ancestor Form require the existing rendered OCR path. Without a configured OCR worker, conversion refuses and creates no output. No hidden extracted text is supplied as a replacement for the visible OCR result. This is conservative: transparency does not necessarily make text invisible, but native extraction cannot establish the visible content safely in that case.

## Evidence

- Six new test methods cover luminosity and alpha masks applied directly and via a parent Form, nondefault blend mode, page-level versus object-level flags, a `/SMask /None` reset counterexample, no output without OCR, and independently reopened DOCX text after controlled adapter recognition.
- Rendered masked pages exactly match a separate heading-only PDF for all four mask/placement combinations. This demonstrates visual absence independently of the extraction guard.
- Cumulative Python suite: **146 tests run, 143 passed, 3 skipped** for unavailable OCR preprocessing dependencies. Compileall passed.
- Unmodified repository guard still reports only 129 reviewed binary assets missing from the partial checkout. No check was bypassed or weakened; only code, synthetic fixture-generating tests and this aggregate report are committed.

## Limits

These tests verify routing and source-text isolation, not real OCR recognition accuracy. Complex stroked contours, blend interactions, soft masks on other object categories and comprehensive visibility classification still need broader validation. This patch is not a guarantee that every concealed PDF character is detected. Actual Word rendering, full repository frontend/build/browser acceptance, full-checkout assets and exact-commit CI remain unverified. No merge, deployment or production-readiness claim.
