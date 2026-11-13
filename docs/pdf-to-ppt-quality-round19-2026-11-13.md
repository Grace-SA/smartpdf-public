# PDF-to-PPT quality round 19 (2026-11-13)

## Scope

Restore eligible editable coverage with a correctly embedded optional CMU Light substitute, without reverting the prior round's renderer/embedded-font consistency fix. No threshold relaxation, merge or deployment. Public PDFs, generated presentations, font files and rendered evidence stay outside Git.

## Implementation

The exact CMU 0.7.0 `cmunbtl.ttf` is pinned at 410116 bytes and SHA-256 `093ceab998d9bb0f4f1312fd10980b3919e557ad594080f7da8c8938a38e4a49`. It becomes a separate regular-only `SmartPDF CMU Typewriter Light` family. All upstream nonidentity font tables remain byte-identical; source timestamps, outlines, cmap, shaping, advances, weight, pitch and fsType=0 are retained. Names are changed across platforms/languages and typographic/WWS fields to prevent regrouping. The complete OFL and modification notice travel with the derivative. Neither uploaded fonts nor unverified operator files are embedded.

Source eligibility is restricted to explicit regular SFTT/CMtt/CMU Typewriter names already mapped to CMU Typewriter Text. Bold, italic, rotation, unknown variants and unsupported raw/NFKC characters are excluded. Four final bounded additive trials (two calibration modes, each with zero or 0.1pt vertical trial offset) retain previous source coverage, XML, order, baseline and rendered pixels; every new word must pass existing geometry/local/whole-page checks. Reports label this a substitute, not source identity. Missing or modified fonts fail closed. Font bytes are revalidated for actual rendering and embedding, not only discovery.

Review removed per-word font re-reading: each candidate pass validates one cmap snapshot while actual rendering/embedding revalidate independently. Regression checks cover refusal boundaries, once-per-pass verification, full table preservation, alias absence, tamper/missing inputs, actual PDF font identity, embedded/unembedded pixel equality, prior content retention, repeated no-op and whole-transaction rollback on retained-pixel mismatch.

## Cross-renderer finding and additional protection

The first implementation passed 787 tests and the existing PDFium gates, adding 32 source positions, but that was not sufficient for release. Independent Poppler source-provenanced ROIs showed worse foreground error at 144/288 DPI. The general word diagnostic abstained because font boxes intersected; an independent source-glyph check confirmed no foreign glyphs inside the actual ROIs. Ink mass was consistently 9–10% below the source, so the difference was not dismissed as sampling noise.

Temporary offset experiments found that a 0.1pt downward candidate passed the original local/geometry/whole-page gates and improved all four resolutions relative to the prior graphic. Larger shifts worsened 216 DPI and were rejected. This single-case result is not treated as a universal correction. The automatic path now additionally requires every final mixed candidate to pass an independent four-resolution nonregression guard, including exact whole-page equality outside the edited ROI union. It compares MAE, foreground error and maximum absolute ink-edge displacement against the previous graphic, with no baseline-error subtraction. The original absolute PDFium thresholds remain unchanged; cross-engine absolute foreground error can still exceed 0.16 and is not claimed to meet that separate diagnostic target.

The guard is fail-closed for missing tools, dirty/empty regions, page-size/rotation mismatches and resource limits. A shared 120-second deadline is checked before optional trials and passed as the remaining budget to every independent validation, rather than multiplying the budget by page count. Existing Office render calls retain their own timeouts and may return after that deadline; no candidate can pass the extra guard after expiry. Final font bytes and source-owner/text/old-shape invariants are still independently checked.

## Evidence

Final cumulative regression: **817 passed, 24 skipped**, one upstream Starlette deprecation warning, 410.51 seconds. The skips require unavailable Mac-specific font prerequisites. Independent helper/recovery/guard review and real-render tests passed. The original 400pt synthetic fixture is retained as a strict dimension-uncertainty refusal because this LibreOffice exports 399.9968567pt; a 432pt fixture covers successful real four-resolution validation without widening the dimension tolerance.

The final wheel includes the new helper, guard and OFL notice; SHA-256 `d6368682cb4b7d0f141c33868e3f657ac002d89b67d508b7bbebb905c934b217`. The repository checker reports only the same 129 approved assets absent from this sparse index, with zero other findings. Full remote-tree preservation is checked before publication.

Final eight-page conversion completed successfully and was independently reviewed after embedding, not inferred from an intermediate candidate:

- Paper page 1: **689 → 721 editable source characters**, 32 added, zero prior source positions lost. The two recovered words use the Light derivative at every actual PDF character, with the exact complete TTF inside the delivered EOT. The third previously refused email remains graphic; this does not restore the old, inconsistently verified 747 count.
- All other seven pages retain their previous source coverage, slide XML, numeric and pixel metrics. No extra numeric tokens on any page. Old textboxes, the original page-error baseline and the graphic outside new source regions remain unchanged.
- Final paper page 1 independent exact words: **146/407**, previously 144/407; strict-box matches remain 0. Other strict-box results and failures remain unchanged. Page foreground MAE improves from 0.126862636 to 0.124414029, not a claim of complete text correctness.
- The accepted final page records a 0.1pt trial and the four verified resolutions. An independent rerun on the actual delivered candidate passed all eight region/resolution observations and found zero changed pixels outside the ROI union at every resolution. MAE, foreground error and maximum ink-edge error all stayed no worse than the previously retained graphic. The original PDFium geometry/local/page gates and source ordering passed too.
- Generic multi-resolution word matching still abstains on the new words because its font-box neighborhood test intersects. The extra production guard does not override that diagnostic: it validates already-proven source ranges, with clean ROI borders and exact outside-region preservation. No blanket isolated-word or source-identity assertion is made.

An earlier final-probe process became unavailable before writing its summary. That incomplete run was not counted; the successful restart and independently inspected final files supplied the results above. GitHub CI is not claimed. Linux LibreOffice Development is not Microsoft Office or production runtime certification.

## Limits

This is a narrowly scoped substitute for common TeX typewriter text, not arbitrary font matching or a promise that every email/table/code block will become editable. The independent strict-box and multi-resolution diagnostics retain failures and abstentions. General PDF coverage, OCR/scans, uncommon fonts, math, cross-client rendering, private-corpus and service/load acceptance remain open. The offline title refit pilot remains excluded.
