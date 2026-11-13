# PDF-to-PPT round 14: public native-recovery diagnostics

## Independent samples and honest scope

Downloaded three official public PDFs: W3C's dummy test PDF, the blank IRS W-9 form, and arXiv's *Attention Is All You Need*. URLs, exact SHA-256 values and selected pages are pinned in `server/pdf-to-ppt/tools/public-native-manifest.json`. Six pages were selected, not all pages of the documents. No source PDFs, extracted text, user data or generated binary artifacts are committed.

The probe exercises native reconstruction, real LibreOffice rendering, content fallback, regional recovery and approved font embedding against a source-image baseline. It does **not** run Stirling or OCR and is not a representative corpus or production-service acceptance result.

Poppler independently extracts source text and words. Word pairing is based on geometry before text comparison, with a strict 2pt edge diagnostic. These parser bounding boxes are not identical to ink bounds. Punctuation token splitting and bbox differences need inspection; the diagnostic does not declare correctness. Character-bag recall is not reading-order accuracy. Missing or raster-only text stays in the denominator.

## Findings and changes

1. **CM-Super misclassified as generic Arial.** The paper uses `SFTT1000` for typewriter text. Explicit standard SF shape codes now select the existing pinned OFL CMU substitutes and preserve regular/bold/italic style. Unknown, small-caps, variable-width, Bright and invisible variants are not inferred. Naming comes from [CTAN's official CM-Super documentation](https://ctan.org/tex-archive/fonts/ps-type1/cm-super/). No CM-Super font program is copied or embedded.
2. **Verified source-word pages skipped safe extension.** Existing regional orchestration excluded pages already recovered with the `source-words` strategy from both bounded extension attempts. The trimmed-spacing retry can recover additional disjoint words while preserving every earlier source glyph, textbox XML and observed pixel. Such pages now receive the same two bounded attempts. All content, source-range, 2pt geometry, regional pixel and original whole-page baseline checks remain unchanged.
3. **Reproducible independent checks.** Added opt-in local tools with pinned sample hashes, new-output-directory protection, Poppler timeouts and explicit diagnostic-only results. The geometry comparator rejects page-count/canvas mismatches and tests demonstrate that swapped numbers cannot be matched merely by text.

## Controlled evidence

- Paper page 1, font mapping alone: editable characters **50 → 143** out of 2,461 independently extracted characters; geometrically paired exact words **14 → 20** out of 407. The strict Poppler box diagnostic remains 3/407, not a claim of independent geometry certification. Whole-page MAE improved from 0.0199424 to 0.0191555; foreground MAE from 0.1513574 to 0.1463711. The additional recovered text was also visually inspected against source and prior output.
- W-9 page 2: controlled retained-word extension **51 → 81** source glyphs and **23 → 34** runs, with **zero prior glyphs lost**. The baseline report was retained exactly. An alternative initial replacement recovered 73 but lost eight prior glyphs, so it was rejected. Extra calibration, Nimbus substitution and optical translation did not provide a safe broad improvement and are not shipped.
- W-9 page 1 already recovered all 4,727 reference characters. Its independent word diagnostic found 929/933 strict pairs; the four unmatched cases were terminal-punctuation segmentation, not established content loss.
- The unchanged dummy input recovered 12/12 characters and 3/3 strict words.

The limited improvements are not enough for general launch. Most text on the tested dense W-9 instruction page and scientific-paper pages is still raster-only. Mathematical glyphs, embedded font substitution and broad cross-client behavior remain unresolved release evidence.

## Verification and boundaries

The implementation has independent code review. New tests cover explicit SF codes and negative variants, operator font availability, geometry-first diagnostics, and source-word extension scheduling. Real-render tests verify retained XML and rollback for both object and word baselines. Independent focused review: 40 tests passed with real LibreOffice. The final tightened retained-XML check covers every prior textbox (not just the first), and its last targeted run plus diagnostic regressions passed 13/13. Full regression and fixed CLI results are recorded below.

Repository hygiene has the existing text-only-checkout limitation: 129 approved binary assets are absent locally; remote assets are preserved, not deleted or allowlisted away. No merge or deployment. GitHub Actions account quota is exhausted; local testing is not claimed as green CI.

## Final fixed-CLI rerun

The committed probe was executed on all three pinned inputs after both fixes. Independent comparator was then run separately against every resulting deck render:

| Selected source page | Editable / reference characters | Geometrically paired exact words | Strict Poppler boxes |
| --- | ---: | ---: | ---: |
| W3C dummy 1 | 12 / 12 | 3 / 3 | 3 / 3 |
| W-9 1 | 4,727 / 4,727 | 929 / 933 | 929 / 933 |
| W-9 2 | 81 / 6,819 | 34 / 1,349 | 34 / 1,349 |
| Attention 1 | 143 / 2,461 | 20 / 407 | 3 / 407 |
| Attention 3 | 13 / 1,534 | 5 / 293 | 2 / 293 |
| Attention 5 | 74 / 2,673 | 16 / 564 | 6 / 564 |

Counts expose missing editability rather than treating retained images as correct OCR. The comparator now also emits identities and counts for unpaired rendered words, including four punctuation fragments on W-9 page 1. Its new regression confirms extra output remains visible. No precision/success verdict is inferred from these counts.

Final full suite with actual LibreOffice and pinned Noto/CMU fonts: **569 passed, 24 skipped**, 264.63 seconds. The final unpaired-output diagnostic regression was added after collection and passed separately (5/5 diagnostic tests), yielding **570 distinct passing tests**. The 24 skips still require unavailable Mac-installed font evidence and are not counted as passes. The last targeted 13-test run also verified the tightened all-prior-textbox XML retention assertion.
