# PDF-to-PPT round 17: atomic collision clusters

## Finding and constraints

The W-9 instruction page's main isolation obstacle is tight leading between lines, not merely gaps between neighboring words on one line. Of 3,672 glyphs excluded by padded-box collisions in the inspected page, 1,959 belonged to components larger than eight runs, 1,344 failed a same-baseline restriction, 264 mixed styles, and 19 had noncontiguous source indices. Only 86 glyphs formed ten strictly adjacent same-line clusters.

Added bounded atomic collision candidates. The complete safe-run padded-box graph is built before cluster eligibility filtering, with unadmitted visible source characters separately protected as obstacles; oversized or unsafe components are rejected whole, never split into apparently safe subsets. Components contain 2–8 runs, fewer than 160 source characters and a maximum 200×50pt footprint. They must share exact style/font attributes, have finite coordinates, disjoint source ranges, no actual ink-box intersection, and no rotation. Every run must match its exact Unicode source range and object ownership, including spaces; generated separators are rejected.

Nearby lines remain separate source-positioned textboxes. There is no concatenation, inferred separator, number reconstruction or movement across omitted source text. Consequently the collision mode can group noncontiguous source ranges while preserving the same text, shapes and background pixels as those independent original runs. A stricter adjacent-only helper remains separately testable.

Unsafe or unadmitted visible source characters are explicit protected obstacles. The original per-word geometry and pixel checks still apply to every member, not a pooled cluster average. Selection, calibration qualification, geometry, pruning and retained-region checks act atomically on the candidate. Any failing member keeps the entire component rasterized. Prior XML, source occurrences, protected pixels and the first whole-page error baseline remain intact. Four bounded additive attempts cover the existing normal and Base Sans fit strategies; previously unavailable strategies are not retried.

## Review and regression coverage

Independent review found two coordinate/provenance bugs before submission: raw character obstacles required the same CropBox/MediaBox origin correction as extracted runs, and generated spaces needed explicit rejection even if PDFium supplied an adjacent object owner. Both are fixed with regressions.

Tests cover transitive components, rejection without partitioning, bounds, incompatible styles/baselines, blocked middle members, raw ink intersections, duplicate owner handling, exact source ownership, generated spaces and cropped unsafe neighbors. Two-column repeated-number fixtures include intervening omitted raster words, source-order restoration, cluster-versus-independent equivalence, prior XML/baseline retention and rollback. The established bounded-retry regression was extended to assert the exact four additional cluster attempts, not removed.

## Public evidence expansion

Manifest version 2 preserves the existing three PDF hashes and original six page identities/order, then appends W-9 source page 3 and Attention source page 6. A regression locks those identities. Raw PDFs and rendered artifacts remain local. The previous committed implementation is rerun against the same expanded eight pages for a controlled comparison. This remains three documents, not a representative launch corpus.

## Remaining limitations

Large connected components, unknown fonts, unsafe source ownership, scans, many mathematical elements and independent ink mismatches remain raster or unresolved. No quality threshold is relaxed. Extra bounded retries add runtime work; production load and cross-client acceptance are still open. No merge or deployment is performed, and quota-limited GitHub CI is not claimed as passing.


A final resource review found that eagerly retaining every neighbor set could grow quadratically before rejecting oversized components. The cluster path now refuses pages above 3,000 safe runs or 100,000 source characters and stops adjacency construction before retaining more than 100,000 neighbor links. It does not split a dense component or change isolated-word behavior. The refusal warning preserves the existing result and prevents subsequent cluster retries on that page.

## Controlled eight-page comparison

| Selected page | Editable chars before → after | Reference chars | Exact paired words | Strict Poppler boxes | Ink within bounds / observed |
| --- | ---: | ---: | ---: | ---: | ---: |
| W3C dummy 1 | 12 → 12 | 12 | 3/3 | 3/3 | abstain: pixel-grid mismatch |
| W-9 1 | 4,727 → 4,727 | 4,727 | 929/933 | 929/933 | 39/226 |
| W-9 2 | 708 → 726 | 6,819 | 264/1,349 | 264/1,349 | 34/78 |
| W-9 3 (new) | 6,342 → 6,342 | 6,342 | 1,310/1,313 | 1,310/1,313 | 18/74 |
| Attention 1 | 747 → 747 | 2,461 | 147/407 | 0/407 | 12/15 |
| Attention 3 | 439 → 439 | 1,534 | 114/293 | 0/293 | 18/23 |
| Attention 5 | 776 → 776 | 2,673 | 180/564 | 1/564 | 28/51 |
| Attention 6 (new) | 599 → 599 | 2,925 | 160/584 | 1/584 | 34/38 |

W-9 page 2 adds **18 source glyphs and six exact/strict words**, with **zero previous glyphs lost**. The other seven pages retain identical coverage and rendered metrics. There are no extra numeric tokens on any page; partial pages still omit many numbers from editable text while retaining source imagery. W-9 page 2's editable coverage is only **10.65%**. Its separate full-page MAE/foreground error changes from 0.0593280/0.1970849 to 0.0592465/0.1968841, a small improvement rather than a breakthrough. Independent ink still fails 44 of 78 observable words and abstains on 1,271 others.

The new W-9 page 3 includes two columns and a table and retains full extracted character coverage, but that is not a claim of perfect visual accuracy: independent ink failures and punctuation-fragment pairing remain explicit. The new paper page 6 retains only 20.48% editable character coverage. Full-page renderings were visually inspected; automated comparisons are not human-labelled ground truth or cross-client certification.

## Final verification

After the resource fix, the complete suite passes **698 tests, with 24 skips**, in 337.85 seconds using real LibreOffice and pinned optional font families. The skips require unavailable Mac-installed fonts and are not passes. One upstream Starlette test-client deprecation warning remains. The final 42-test collision/resource subset passes with real rendering, including actual displacement of one cluster member, unchanged outside-union pixels, embedded font identity, text/numbers and source-order mapping.

The first cumulative run exposed a legacy test double that did not accept the two new candidate options. Its signature now explicitly forwards those options; all original assertions remain unchanged. Its real-render three-test rerun passes, followed by the complete passing run above. No failed assertion was removed or made less strict.

All eight public pages were rerun on the final resource-guarded implementation. Coverage, numeric/pixel metrics, strict-box diagnostics and fixed-grid ink measurements exactly match the table above; graph budgets were not hit. A wheel build and isolated import verify the new module and graph-budget behavior are packaged. Compilation and changed-file whitespace checks pass. The repository checker reports only the known 129 approved binary assets missing from the sparse local index; publication contains text-only changes and preserves every other remote blob.
