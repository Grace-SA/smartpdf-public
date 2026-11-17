# Touching-glyph OCR word spacing

Follow-up to `41fd175139d111dfacf27f1acd732482524b9ddc`.

## Narrow extension

The existing one-projection-component-per-letter path remains intact. A second bounded path handles ASCII alphabetic runs of 6–32 letters whose touching strokes produce fewer projection components than letters. It requires all of:

1. Original confidence >=0.95 and horizontal, in-bounds geometry.
2. Between one and three large blank pixel gaps separating word blocks.
3. Two padded whole-line recognitions agreeing on the identical spaced string.
4. Removing those spaces must exactly reproduce the original letters.
5. Two recognitions of every pixel-separated word block matching the corresponding whole-line word.
6. Every recognition confidence finite and within [0.95,1], with a complete well-formed batch.

No digits, punctuation, existing spaced text, low-confidence content or non-ASCII text is eligible. No star/asterisk replacements are performed. Each invocation recognizes at most eight candidates, with 6–10 small crops per candidate. Repeated passes use the same model and are **not** an independent guarantee of correctness.

## Review and evidence

- Independent review reproduced an empty-crop regression with a zero-width OCR box: the old path skipped it, but the new helper initially called OpenCV on it. The final helper rejects zero-width crops; an integration regression exercises both paths through the public `recover_spaces` function.
- Six focused synthetic tests verify positive pixel/recognition agreement, exact-letter preservation, rejected mismatches/malformed or uncertain recognition, unsupported strings, no-gap rejection, budget behavior and the empty-crop regression. Model outputs in these synthetic protection tests are mocked and do not prove recognition accuracy.
- Final pinned-model cumulative regression: **243 tests, 242 passed, 1 skipped**, 89.271 seconds. The skip remains external Stirling without `STIRLING_URL`. Six new and four prior spacing tests also pass in independent review.
- Actual public WEB-009 local rasterization: only G1 changes, `BloodPressure` becomes `Blood Pressure`. Native-reference exact strings increase from 117/123 to 118/123. The 123 nonempty positions, five merged ranges and page-context comment remain unchanged. This is a single synthetic raster test, not a general accuracy estimate.
- `AndhraPradesh` remains unchanged because its word-block recognition scores are below threshold. All four incorrect stars remain unchanged rather than guessing their intended punctuation.
- Public real-scan WEB-024 remains successful with identical values and merged ranges.
- New helper/tests pass Ruff and Python syntax checks. The fingerprint includes the new helper. Sparse repository guard remains blocked by the same 129 locally missing approved assets; remote binaries are not modified.

## Remaining blocker

Remaining ambiguity cannot safely be resolved by global DPI changes, string replacement, or lowering confidence thresholds. Broader rollout confidence needs a larger labelled real-scan corpus, including touching fonts, low-quality captures, multilingual text and punctuation. The historical private corpus and full production acceptance environment are not available here. No general release claim, merge or deployment; CI still requires usable Actions quota.
