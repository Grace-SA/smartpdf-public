# PDF-to-PPT quality round 20: inferred separators and atomic recovery

## Scope and root cause

This round investigates missing editable text on the same fixed, hash-checked eight-page public corpus. The experiment is native recovery over a source-image baseline, not Stirling service acceptance. No public PDFs, font binaries or rendered pages are committed.

PDFium can infer a trailing ASCII space for a positioned PDF word. The previous exact-owner verifier correctly refused that generated character, but also refused the whole collision component. In the four selected paper pages, copied trimming of exactly one generated terminal space makes 31/23/39/39 complete components eligible for strict source verification, representing 2,690 potential visible positions. Eligibility is not successful recovery.

The copy-only normalization is deliberately narrow: original Unicode and range must match exactly; all preceding characters must be non-generated; the preceding character cannot be whitespace. Literal, internal, repeated, non-ASCII or visible generated characters are unchanged. The exact owner verifier is unchanged. Original collision topology, blocked pixels, component bounds and individual textboxes remain intact. No words or numeric tokens are concatenated.

## Strict acceptance

The optional additive stage runs last, after prior original-font, BaseSans and Light attempts. It retains all existing source ownership, content, 2pt geometry, local/page pixel, original baseline, prior XML and pixel gates. It does not introduce another font substitute.

A new independent Poppler assessment renders the original, retained and trial pages at 144/216/288/432 DPI. Per-region uncertainty rejects that region; global input/resource/deadline/outside-region failures reject the whole assessment. A component survives only if every member passes. Malformed assessment lengths or non-boolean results reject all components. The deck is rebuilt using only complete passing components, rendered again, and checked by the unchanged final four-resolution verifier. Screening alone cannot authorize a result. Both fit attempts share a 120-second validation deadline, and already resource-refused pages are not retried. Existing Office calls retain their own timeout; expiry cannot authorize a candidate.

## Experimental evidence, not final acceptance

Unrestricted normalization admitted 221 extra source positions under the existing PDFium gates. Independent four-resolution measurements rejected almost all of these: only two complete components, 18 positions, passed every member check. The rejected candidates remain graphic, not partially editable. The retained candidates are `of` / `the` on paper page 1 and `layers.` / `second` on paper page 3. A rebuilt, embedded prototype independently passed the unchanged four-resolution verifier on both changed pages.

The IRS W-9 dense second page has a different dominant problem: small 8pt HelveticaNeue Roman, close lines and mixed-style collision components. Approximately 3,856 missing visible positions can already reach existing candidate discovery, so merely expanding discovery does not solve the problem. Experimental ±0.2pt vertical trials yielded up to 21 candidate positions and are not implemented. The −0.2pt candidate was independently embedded and rendered: text and numeric order matched, but the unchanged strict guard refused before local scoring because the source page is 611.976013 × 791.968018pt while both retained and candidate LibreOffice pages are 611.971680 × 791.971680pt. This is a concrete page-geometry quantization barrier, not a successful recovery; no dimension tolerance was widened. Large collision caps and strict visual thresholds remain unchanged.

## Verification status

The first official eight-page conversion completed through the normal content fallback and font embedding path. An independent check of its actual final files found:

| Public pages | Editable source characters before → after |
| --- | --- |
| Dummy page 1 | 12 → 12 |
| W-9 pages 1 / 2 / 3 | 4,727 / 726 / 6,342 → unchanged |
| Paper pages 1 / 3 / 5 / 6 | 721 / 439 / 776 / 599 → 726 / 452 / 776 / 599 |

Only 18 new visible source positions in two whole components were accepted. Every previously accepted source position and textbox XML remains; the other six slide XMLs are identical. Actual rendered text and ordered numeric tokens equal the editable PPT text on all eight pages, with no source-extra numeric tokens. Final embedded changed pages pass all four independent resolutions, including exact outside-ROI pixel preservation. Independent component reconstruction confirms there is no partially accepted component. These checks do not imply that the still-graphic source text is editable or fully recognized.

Independent review fixed malformed assessment handling, duplicate warnings and retrying a resource-refused page. Tests cover immutable normalization, exact owners, preserved collision topology, numeric separators after embedding/rendering, whole-component screening, rebuilding with only retained ROIs, and byte-identical rollback on final verification failure. Controlled-guard tests verify transaction plumbing only, not visual correctness. Existing call-count and wrapper tests were updated explicitly for the two new bounded stages, without relaxing existing content/visual assertions.

Final-code cumulative regression: **857 passed, 24 skipped**, one upstream Starlette deprecation warning, 418.08 seconds. The skips retain unavailable Mac-specific prerequisites. The wheel SHA-256 is `ff58f909a2896de2d87ed72fea1cb1ad67ea1bc0f57c9ded114c6ef67423958e`. The repository checker reports only the same 129 approved assets absent from this sparse index and zero other findings; all other remote blobs are preserved when publishing. The repeated final-code eight-page conversion also completed. All eight final slide XMLs and reported metrics match the first official run exactly. A fresh independent check of the repeated final embedded files passed source coverage, prior XML, actual ordered text/numbers and four-DPI verification on both changed pages. The prototype is not used in place of final delivery evidence.

## Remaining limits

This is conservative, partial editability, not general release certification. Dense small-font text, mathematical content, scans/OCR, mixed-style components, arbitrary font substitutions, Microsoft Office/client parity, service/load behavior and the unavailable private corpus remain open. A source-image fallback preserves appearance but does not count as editable content. GitHub CI is not claimed because account minutes are unavailable. No merge or deployment is authorized by this work.
