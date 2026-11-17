# Native leader punctuation and strict public regression

Baseline engine: `b033dff580df9c9d161758f9d88c43018d61b79a`. This round couples a reproducible public scoring protocol with a narrowly evidenced native-table correction.

## Reproduced defect

In public ICDAR US-001, ten numeric cells inherited the last dot from the preceding row label. For example, a number was exported with an extra dot and space before it. The source geometry is unambiguous in those rows: the misplaced glyph continues the label's regular dot rhythm, while a much larger gap separates it from the first digit. Both neighbouring source strings retain the glyph, but it belongs to the wrong cell.

The new recovery moves that one native dot back to the row label only when at least three non-overlapping rows support the same boundary. It requires exact native glyph content, a single horizontal baseline, matching dot font/size/rhythm, a large gap before the number, visible finite geometry and no physical vertical separator between the dots. Merged/multiline, rotated, cropped or inconsistent candidates remain unchanged. Only already decimal-valued forms with an extra isolated leading dot qualify; legitimate `.18` remains unchanged. All non-whitespace source characters are conserved, numeric characters are never inferred, and source font bounds follow the corrected ownership. A result warning identifies affected pages.

## Visual regression found and fixed

Cell scores alone missed a presentation regression: after correcting ownership, the existing font-based width refinement could reject a new midpoint beyond its 30% movement budget and fall back to a narrower model column. LibreOffice rendering then wrapped formerly single-line row labels.

The final fix is confined to the recovered first boundary: allow a rightward move capped at the existing 30% budget **only if that capped position remains inside the whitespace gap between every verified left and right glyph**. No marker, negative move, or glyph-cutting proposal gains permission. Other boundaries keep their existing rules. The corrected real workbook was reopened and rendered by LibreOfficeDev 26.8; labels remain on one line and the numeric prefixes are corrected. This is a compatibility/visual smoke test, not Microsoft Excel acceptance or a pixel-perfect page reconstruction claim.

## Evidence

- Twelve original synthetic leader tests cover glyph conservation, source immutability, three-row consensus, valid leading decimals, separators, font/spacing disagreement, merged/multiline cells, crop/rotation/nonfinite geometry, pipeline warnings and bounded non-clipping column refinement.
- Independent reviews found no remaining blocker in the restricted path. The production logic has no sample IDs, annotation reads or expected values.
- Final pinned-model cumulative regression: **274 tests, 273 passed, 1 skipped**, 87.651 seconds. The skip still requires external Stirling. Twelve focused leader tests and the new boundary refinement also passed independent review.
- Final fixed public comparison: **12/12 exports both before and after; no position-sensitive or row-aligned score regressions**. Only US-001 changes: 20 corrected cells, with unchanged table count, merged ranges, comments and non-whitespace character multiset. Exact text at position rises **2,257 → 2,271**; normalized text-and-span at position **2,295 → 2,315**; row-aligned normalized text-and-span **2,508 → 2,528**, all over the same 2,548 annotated nonempty cells. Both cohorts use the same 12 files, 39 pages, pinned models, one worker and a 180-second per-file budget. Scorer v3 verifies the actual source, label and output bytes and binds the scoring report to its benchmark/manifest; the engine fingerprint is checked before and after each run.
- Independent artifact inspection confirmed exactly 20 changed cells in US-001: ten numeric fields and ten labels. Non-whitespace characters, merged ranges and comments were preserved. The final column-width fix does not alter cell strings.

## Remaining coverage work

US-002 still has multilevel header and section-row structural errors. Read-only tracing found duplicate line/rectangle edges for one thick underline, disagreement between model header rows and physical levels, and multiple body-recovery constraints (currency, standalone footnote marks and wrapped section headings). These are public reproducible issues; further work is **not** wholly dependent on private samples. Simply relaxing a global threshold or using annotation strings would be unsafe.

The fixed corpus is not representative of all PDFs or an established held-out model test set. File-export success is not correctness. Full device/Office validation, broader multilingual/scanned coverage and successful CI remain outstanding. Repository guard still reports 129 approved assets absent from the sparse local index; no remote assets are removed. Only code, public provenance metadata, aggregate evidence and original synthetic tests are committed. No merge or deployment.

Final comparison JSON SHA-256 (local aggregate evidence, not uploaded): `63361b8b297a1ac35d69732847e7c6450a5fb1201d88c069cc8a07963134d212`.
