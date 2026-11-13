# Conservative native text-layer header order

Baseline engine: `72c0cb9756e6a9e447b70f8657c11b2c1dbae8c3`.

## Reproduced scope

Public US-007 has four headers where the native PDF text layer places a grade number on the first line and `Grade` on the second, but model cell text reverses those lines. Both lines use the same font and size with ordinary line spacing; they are not superscript footnotes. `Grade 1` is semantically equivalent to the source arrangement, so this is a source-order fidelity issue, not a claim that the original grade meaning was wrong. US-010 similarly has one header containing `Launch:` above its date, with the model text in reverse order. The real source crops were visually inspected.

The new optional helper applies only to unmerged ASCII headers with two or three clearly separated horizontal native baselines, identical font/size, exact word-multiset equality and unambiguous glyph ownership. It neither adds words nor changes numeric tokens. Bounded font-metric tolerance (at most 1.5 points and 15% of the font size) admits the complete glyph envelope when model and PDF font metrics differ slightly; the original model bbox is not expanded. The entire evidence region is checked for extra glyphs and competing cell claims. Any overlapping annotation, including empty-Contents appearance streams, or source image causes rejection. Unknown/malformed metadata, non-LTR/non-ASCII text, viewport clipping, abnormal gaps and budget excess keep the previous result.

## Review limits

Independent review reproduced malformed row-index/span cases that initially still reordered text. Strict dimensions, index ranges, span consistency and occupied-slot uniqueness were added before integration. The sequence of existing recovery steps remains unchanged; the final text-layer step was appended using an explicit, reviewed pipeline instead of increasingly nested calls.

This evidence is **native text-layer order**, not a general rendering-visibility proof. A real invisible `Tr=3` text stream still supplies glyphs to pdfplumber; opacity, vector occlusion and arbitrary internal PDF clipping are not fully observable through that API. Image/annotation exclusions do not solve those problems. The five inspected source examples are visibly rendered, but that case evidence must not be generalized into a visibility guarantee. No OCR or multilingual reading-order claim is made.

## Validation

- Final tested-change-set regression: **311 tests, 310 passed, 1 skipped**, 83.288 seconds. The skip is the external Stirling integration. Nine new helper tests, full Ruff on new files and critical legacy integration checks pass. Independent review verified the final metadata fix and exact pipeline ordering.
- Both pinned cohorts were rerun with frozen engine hashes: **22/22 PDFs / 70 pages** export, with **no strict or aligned regressions**. The original twelve-file cohort is unchanged. In the second ten-file cohort, normalized text at position improves **928 → 933 / 951**, normalized text-and-span **924 → 929 / 951**, row-aligned normalized text **943 → 948 / 951**, and aligned text-and-span **939 → 944 / 951**. Exact text improves **904 → 910 / 951**.
- Direct artifact verification finds the five intended token-order changes plus one whitespace-only header change: existing source typography now restores the three-line `Age 3` header in US-007. Its first two column widths also refine, so this is not described as byte-identical styling. Across both cohorts, all cell token multisets, numeric tokens, nonempty-cell types, source-context comments, sheet dimensions and merged ranges are preserved. Final engine fingerprints match both benchmark records.
- All three affected worksheets were reopened and rendered in LibreOfficeDev 26.8. The corrected source example headers and the downstream width/soft-wrap adjustment are readable without newly observed clipping. This is not Microsoft Excel/device acceptance or a universal visibility proof.
- Repository guard still reports only the 129 approved assets absent from the sparse local index; no remote assets are removed. Historical optional table-count checks remain explicitly unverified. Source/annotation/output files remain local; only code, original synthetic tests and aggregate/provenance evidence are committed. No merge/deployment or general production certification.

Local comparison SHA-256 values:
- excel-icdar-native-order: `17be45a34efe109e33c75632f7ed6838515a923c5957cda80db744ebc3edb3dc`.
- excel-icdar-next-native-order: `aa5d2c1ed166b3415703f7592989a02291d9f8ac7d042d10b657d38e82705cb5`.
