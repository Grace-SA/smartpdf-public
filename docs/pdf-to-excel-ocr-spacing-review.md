# Conservative OCR spacing follow-up

Follow-up to `7efbcf1cb337316f93770f69dc9a6a6f64b7b30d`.

## Defect and repair

The existing pixel-supported space recovery requires two high-confidence recognition results to agree. Review found that `all()` over an empty result is true, and a single result also passed the old predicate. Missing/incomplete OCR results could therefore insert spaces without the promised consensus.

The repair requires the recognition result count to exactly equal the crop count, well-formed result rows, and both corresponding confidences to be real, finite and in [0.95,1]. Empty, short, surplus, malformed and invalid-confidence responses leave the original text unchanged. Regression cases cover these conditions.

Padded recognition sometimes returns extra whitespace at the outside edges of the crop. The comparison now strips only ASCII boundary whitespace before checking exact internal text. It still requires one-to-one character projection, a sufficiently large blank pixel gap, two recognitions, unchanged letters and the original confidence threshold. Existing words, numeric strings and CJK remain ineligible. No punctuation is substituted and no model is added.

## Measurements

- Final pinned-model cumulative regression: **237 tests, 236 passed, 1 skipped**, 79.644 seconds. The skipped test still requires external Stirling. Four focused spacing tests also pass independently.
- Fixed local rasterization of public WEB-009: the only changed table cell is B1, from `NutritionalAssessment (No. of individuals)` to `Nutritional Assessment (No. of individuals)`. All other values and merged ranges are unchanged. Exact native-reference string matches increase from 116/123 to 117/123. This is one synthetic rasterization, not a general accuracy measure.
- Public real-scan WEB-024 still converts successfully with identical values and merged ranges.
- Separate DPI experiments found 144/216/288/360 DPI achieved 116/115/116/116 exact matches before this repair. Higher DPI did not provide a safe general improvement, so render resolution is unchanged.
- Remaining `BloodPressure` and `AndhraPradesh` have touching glyphs and fail the one-character/one-projection-component rule. Partial experiments suggest possible word-block recognition, but this needs separate validation. Low-confidence star/asterisk disagreements are not rewritten.
- Source/test syntax and critical Ruff checks pass. Sparse-index repository guard is run and still reports only 129 missing approved local assets; those remote assets are left unchanged.

No private inputs, public sample PDFs or raster outputs are committed. No merge/deploy or general-production accuracy claim. Successful CI and real-device/representative-real-scan acceptance remain outstanding.
