# PDF-to-PPT round 16: independent ink evidence and additive font recovery

## Independent font-box investigation

The paper's source Nimbus Roman regular descriptor reports ascent/descent 678/-216; the complete generated Termes regular face reports 1055/-281, covering its wider accented repertoire. Bold has the same kind of difference. Consequently some Poppler text boxes differ even where visible ink is correctly placed. Shrinking complete font metrics to hide this difference risks clipping supported characters and is not an acceptable repair.

Added `tools/public-native-ink.py`, a separate diagnostic using Poppler rasterization at a fixed 216 dpi. It never registers, shifts or rescales images. It pairs words by mutual nearest geometry before comparing exact normalized text, and observes only isolated word crops with a solid shared border and nonempty ink. Neighbor intersections, pixel-grid differences and ambiguous geometry explicitly abstain. Edge displacement and foreground difference remain separate measurements; identical bounding extents alone cannot pass changed glyphs. The output explicitly disclaims an acceptance verdict and never modifies the original strict-box results.

Input limits include 64 MiB per PDF, 20 pages, 2,000 words per page and bounded pixel dimensions. Text extraction is bounded before parsing with a 21-page extraction cap, 8 MiB XML limit, POSIX child file-size enforcement and a 60-second timeout. Unsupported platforms fail explicitly; temporary files are cleaned on failures. The test suite covers identity, shifts, altered glyphs with unchanged outer bounds, wrong text, repeated-text geometry, abstentions, resource guards and cleanup.

Six-page previous-round remeasurement yielded 12/15, 18/23 and 28/51 observed paper words within the diagnostic ink bounds. Most words abstain, not pass. The paper title still exposes genuine ink mismatch. W3C's one-pixel raster-grid discrepancy explicitly abstains rather than being aligned away. These findings explain only part of the strict-box discrepancy, not all failures or any general launch readiness.

## Scope and remaining barriers

No quality gate is relaxed. Raw public PDFs, font binaries and generated evidence are not committed. The small public corpus remains diagnostic, not independent human-labelled coverage of common PDFs. Generic fonts, scans, mathematical content, cross-client PowerPoint/WPS/Mac behavior and production-runtime/load acceptance remain open. No merge or deployment is performed; quota-limited GitHub CI is not represented as passing.

## Additive alternative-font recovery

The dense W-9 instruction page uses embedded `HelveticaNeueLTStd-Roman`. Its generic Arial substitute was a poor proportion match. Two bounded additive attempts now try the existing pinned, BSD-licensed `SmartPDF Base Sans` font: median-character height first, then word bounds. This is explicitly a reviewed substitute, not an assertion of source-font identity. Only exact regular `Helvetica` and `HelveticaNeueLTStd-Roman` names (with an optional six-uppercase-letter PDF subset prefix) qualify. Bold, italic, rotated runs, already-selected Base Sans and missing raw/NFKC Unicode glyphs are excluded. No new fonts, system-font dependency or network access is introduced.

Every accepted word still passes the existing geometry, region-pixel, retained-pixel and whole-page gates. Previously accepted source ranges and textbox XML remain intact, and the original baseline error allowance is retained across retries. A review improvement preserves prior warnings through each extension; reports identify the substitute and calibration mode. Synthetic real-render tests verify both modes, old XML retention, unchanged baseline, rollback after a failed retained-pixel check and actual embedded-font output text/numeric tokens.

More complicated per-character formatting experiments were rejected: one gave no improvement; another added only two characters while increasing formatting complexity. They are not included in production code.

## Final reviewed-code public rerun

| Selected page | Editable chars, previous → current | Independent reference chars | Exact paired words | Strict Poppler boxes | Fixed-grid ink within bounds / observed |
| --- | ---: | ---: | ---: | ---: | ---: |
| W3C dummy 1 | 12 → 12 | 12 | 3/3 | 3/3 | abstain: pixel-grid mismatch |
| W-9 1 | 4,727 → 4,727 | 4,727 | 929/933 | 929/933 | 39/226 |
| W-9 2 | 104 → 708 | 6,819 | 258/1,349 | 258/1,349 | 32/74 |
| Attention 1 | 747 → 747 | 2,461 | 147/407 | 0/407 | 12/15 |
| Attention 3 | 439 → 439 | 1,534 | 114/293 | 0/293 | 18/23 |
| Attention 5 | 776 → 776 | 2,673 | 180/564 | 1/564 | 28/51 |

W-9 page 2 adds **604 source glyphs with zero previous glyphs lost**, in two steps 104 → 483 → 708, and retains the original baseline. All other sampled pages retain identical coverage and rendered metrics. There are no extra numeric tokens; many source numbers remain raster-only. Editable coverage of the instruction page is still only **10.4%**, not general-purpose success.

The dense page's regional final MAE/foreground error improves from 0.0325589/0.1525666 to 0.0309982/0.1463272. The separate public-probe full-page metric improves from 0.0632968/0.2074245 to 0.0593280/0.1970849. These use different render grids and are not interchangeable acceptance measurements. The new independent ink diagnostic is stricter/different again: 42 of the 74 observable instruction-page words remain outside its bounds; another 1,275 words abstain. Do not interpret passing font boxes or exact extracted text as proof of matching visible glyphs. The final page rendering was visually inspected, but this is not human-labelled corpus certification.

## Verification and review closure

Final cumulative run after all review fixes: **655 passed, 24 skipped**, 324.67 seconds, with real LibreOffice and the pinned optional font families. The 24 skipped tests require unavailable Mac-installed fonts and are not passes. One upstream Starlette test-client deprecation warning remains. The focused final 24-test Base Sans run also passes actual EOT embedding and rendered text/numeric preservation. All six public pages were rerun after the final warning-uniqueness fix: coverage, numeric metrics, rendered metrics, strict-box diagnostics and independent ink results are identical to the table above; the substitute warning now appears exactly once.

Review fixes included bounding XML extraction before parsing, retaining prior warnings through extensions, deduplicating the substitute warning, and distinguishing substitute selection from source-font identity in the README. Source compilation and changed-file whitespace checks pass. The repository checker reports only the known 129 approved binary assets absent from this sparse local index; no raw PDFs or new binaries are added, and publication preserves every unchanged remote asset blob.

Read-only follow-up analysis identifies a larger remaining bottleneck than bold-font coverage: isolated-word admission allows only 2,952 of 6,464 regular W-9 instruction-page glyphs into recovery tests. A future bounded adjacent-word cluster must preserve complete ownership, literal spaces and neighboring pixels rather than shrink exclusion margins. Of 42 observable ink failures, 41 have a one-pixel edge difference at 216 dpi; multi-resolution fixed-coordinate comparisons against an image-baseline control could distinguish physical mismatch from sampling, but these failures are not waived now.
