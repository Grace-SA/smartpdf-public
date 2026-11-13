# Reject contradictory scan column geometry

Baseline: `d060966739536b213d5cb4075ad60ab4f97d58e2`.

## Reproduction and boundary

An isolated Docling/RapidOCR experiment reused exactly the twelve raster pages from the Word grid-probe research. It produced20 candidate tables against19 annotated regions. Two candidates have a readily reproduced internal contradiction: their assigned left-to-right column indices disagree with their own OCR text boxes. In EU-002, year2004 is assigned column5 although its box lies to the left of column0's value34.7. The same issue occurs in subsequent rows. US-006 also has reversed cell assignments.

Important routing distinction: the existing Excel converter normally handles both of these particular raster PDFs through its ruled-grid path, which exports their columns correctly. They do not prove an existing normal-route Excel wrong-year bug. They reproduce a latent failure in the Docling structure fallback and show why directly adapting those candidates to Word would be unsafe. This change guards that fallback only. No Word adapter is enabled.

## Necessary consistency check, not an accuracy certificate

After the existing structural adapter validates cell coordinates and overlaps, inspect nonempty single-row/single-column cells that have text boxes. Group by model row, sort by column index, and compare neighboring eligible cells. Reject only when the earlier column's box is strictly to the right of the later column's box and their vertical intervals positively overlap. Both supported coordinate origins are normalized using page height. Malformed or unknown supplied geometry is refused. Sorting plus a linear pass avoids quadratic pair comparisons.

No value is reordered, corrected, dropped or inferred. One contradiction raises an error for the entire conversion, even after another valid table was found. It does not fall through to aligned-text recovery, publish a partial workbook, or overwrite an existing output.

These boxes come from the same model pipeline, not an independent ground-truth detector. The check establishes internal inconsistency only. Missing boxes, merged cells, nonintersecting text lines and nonadjacent inversions hidden by overlapping intermediate boxes remain outside this narrow proof. Absence of a contradiction is not evidence of full correctness. Unknown direction/layout conventions may be conservatively refused rather than silently repaired.

## Validation

- Ten original synthetic tests cover shuffled input order, cyclic/reversed columns, mixed coordinate origins, separate rows/lines, spans, absent boxes, touching/overlapping geometry, malformed numbers/origins, immutability and a20,000-cell ordered row.
- The integration regression provides a valid table followed by a contradictory one and checks whole-result refusal, no aligned fallback, no new output, preservation of an existing output and unchanged source bytes.
- Replaying all20 frozen public-derived candidates rejects only EU-002 and US-006. This is a gate audit, not a new full-corpus conversion run and not an endorsement of the other18 candidates.
- Normal end-to-end runs of those two original raster PDFs still use one ruled-grid table each and preserve their source bytes. The explicit forced-fallback experiment bypasses that grid result to test actual Docling inference and the production refusal path; this intervention is not hidden as ordinary routing.

Final pinned-model suite: **392 tests, 391 passed, one external integration skipped**, 92.661 seconds. The unpublished background prototype remains excluded. An initial run from a shared temporary script directory failed because an unrelated `mlx` directory was mistaken for an installed optional backend; rerunning from an isolated script directory resolved the import collision without changing dependencies. Those failed runs are not counted as validation passes.

Both real forced-fallback runs now stop with the explicit column-conflict error, preserve the previous output bytes, and leave source hashes unchanged. Independent review found no blocking issues and ran four additional state/fallback checks. New-test Ruff checks, critical engine lint, formatting and whitespace checks pass. The repository guard still reports the same129 missing approved binary assets in the sparse local workspace; publication retains the remote base tree and changes only the four reviewed text files.

No new source PDFs, OCR text, model output artifacts or model weights are committed. The wider public comparison already demonstrates additional recognition, merged-cell and extra-table errors that this narrow consistency gate does not solve. No general-production, trustworthy Word fallback or100% recognition claim is made.
