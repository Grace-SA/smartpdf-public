# PDF to Word: native coverage for rotation-encoded upright pages

Base: `58cbe2bbabc4e6354a950da551d62dec4cc80221`; branch `codex/pdfword-general`.

## Coverage change

Previously every page with rotation metadata required OCR, even when its text was visually upright because its content matrix counterbalanced the page-view rotation. That unnecessarily introduced recognition dependency and potential errors for otherwise readable native PDFs.

After original-input preflight, the worker now normalizes supported page-view rotations in a temporary private copy using the pinned pypdf implementation. Native extraction then applies the existing geometry, clipping, visibility and table safeguards. The user's source is not rewritten. Actual sideways text, hidden/clipped text and scans still require the guarded OCR path; no OCR accuracy claim is made.

Annotation geometry is not rewritten because pypdf's content transform does not transform annotation appearances. Annotated pages retain their original rotation and conservative processing, including within mixed documents. Noncanonical equivalent angles are bounded to signed 32-bit values and canonicalized before transformation, preventing huge-angle disagreement between PDF parsers.

Normalization is covered by the existing whole-task time limit, with additional limits of 8 MiB expanded content instructions per transformed page, 64 MiB cumulative transformed instructions and 60 MiB normalized output. Unchanged image/font streams are not expanded by this step. Empty/null page contents remain valid. These limits may conservatively reject unusually complex vector pages and are not production load-test evidence.

## Verification

- Six original synthetic upright-native cases (90/180/270 degrees, each with and without a CropBox) improved from **0/6 without OCR on the base worker to 6/6 without OCR on the new worker**. This is a targeted case result, not overall corpus coverage.
- PDFium rendering before versus after normalization matched pixel-for-pixel in all six cases. Equivalent -270, 450 and 360000090 degree cases also matched. Extreme out-of-range rotation is refused instead of silently changing geometry.
- Fifteen new regression tests include editable native tables, mixed rotations, source immutability, crop dimensions, annotated pages, hidden/clipped text, genuine sideways text, encrypted-input preflight, cancellation, page/aggregate instruction limits and a mixed document containing a rotated null-content blank page.
- Final available PDF-to-Word Python suite: **90 passed, zero skips**. Python compilation passed.
- The six generated DOCX files passed independent package validation and LibreOffice rendering. All had one output page and exact `Editable 123.45` text; crop dimensions matched within output-unit rounding. One cropped output was visually inspected. Native table editing/save/reopen and source-page markers were tested separately.
- Independent review discovered the extreme-angle geometry disagreement and a null-content regression introduced by the resource check. Both were fixed with explicit regressions before publication.

## Remaining gates

The private 139-input corpus and original OCR models remain unavailable here; no real-corpus rate or OCR accuracy was recalculated. Actual Microsoft Word, full-site/browser regressions and production performance acceptance remain outstanding. The unchanged repository guard was executed and remains blocked by 129 existing assets absent from the partial local checkout. Publication preserves original remote assets and unrelated files. GitHub Actions quota is exhausted according to the user, so local success is not successful exact-commit CI.

Only source/tests and this report are published. No private samples or rendered outputs are committed. No merge/deployment is performed, and general production readiness remains false.
