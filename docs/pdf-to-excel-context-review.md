# PDF-to-Excel page context preservation review

## Scope

This follow-up to `3f6e09e735f6b51467838b563b1f8ef5e9ef1473` preserves bounded native page text outside all detected table rectangles as an Excel comment on the first cell of that page's first table. The user-facing result explains where comments are stored and that context may be incomplete. This retains titles and explanatory footnotes without changing table cells, inferred types, sheet counts or merged ranges. It does **not** infer which asterisk belongs to which note. Comments are not normally printed or visible without opening them; this is evidence preservation, not visual page reconstruction.

Only glyphs fully inside the visible media/crop intersection and fully outside every table boundary qualify. Pages with unknown/invalid table rectangles, mixed-direction context, unsupported controls/XML characters or context over 16,000 characters are not guessed or silently truncated. Scanned notes are not recognized by this path. The total extracted-text budget now includes context.

Mixed-orientation native pages remain unsupported without the existing conversion server. Majority orientation is not sufficient evidence to rotate minority text safely. A new conversion regression asserts that the mixed fixture still refuses and writes no output. This round does not claim mixed-orientation coverage improved.

## Review findings fixed

- The independent review found that XML-forbidden Unicode characters in a comment could turn an otherwise successful table conversion into a serialization failure. Validate full XML 1.0 character ranges; reject unsupported context rather than rewrite it. Regression includes U+FFFE, U+FFFF, isolated surrogate, NUL and over-budget text.
- Combining context comments and native form-rule drawings in a single sheet exposed an existing drawing inserter's invalid OOXML child order. Insert `drawing` before `legacyDrawing` and other schema-following elements. The new integration regression checks element order, internal relationships, comment text, cells and merged ranges. It fails against the old inserter and passes after the fix.

## Validation

- Final pinned-model cumulative regression: **231 tests, 230 passed, 1 skipped**, 77.913 seconds. The skip remains the external Stirling rotated-conversion integration because no `STIRLING_URL` is configured. This includes five new context cases, a mixed-rotation refusal case and the comment/form drawing regression.
- New context/rotation test and context source files pass Ruff; changed older modules pass critical-error Ruff checks and Python syntax compilation. Broad modern Ruff rules still flag pre-existing style/exception patterns in the converter; they are not claimed clean.
- Replayed the same frozen 12-public-PDF pilot from the rotation review, using identical pinned models/runtime. Outcome remains **11 outputs, 1 expected refusal**, with no timeout or unhandled error. Every one of the 11 successful workbooks retains identical canonical cell-value/merged-range hash to the prior candidate. The mixed-direction WEB-010 remains refused.
- Seven PDFs now preserve eight page-context comments. WEB-009 now includes its table title, `* Data not available` and page footer. Independent inspection confirms all 123 nonempty cell values/types/positions and five merges remain identical, and all eight workbook relationships are internal. Context interpretation is not inferred.
- Local aggregate pilot-results SHA-256: `8b82c1e166ce0c154463a41d93f074064a2d5903c8c7a948b30819b5e829621f`. This pilot does not replace or remeasure the historic 200-file corpus.

Only original synthetic test generators and this aggregate report are committed. Public pilot inputs/outputs remain outside Git, and no private user samples are uploaded. Sparse-checkout repository guard still reports approved binary assets missing from the local index; it is not described as passing. Existing asset blobs are retained unchanged by applying only the reviewed source/test/document files to the remote base tree.

## Remaining release gates

Not general-production acceptance: larger reviewed corpus, scanned footnotes, mixed text directions, document-wide semantics, production latency/load, native Excel/LibreOffice comment rendering, browser/device acceptance and successful CI remain outstanding. The user's depleted GitHub Actions quota is not bypassed. No merge or deployment is authorized by this work.
