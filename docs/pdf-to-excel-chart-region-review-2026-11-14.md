# Separate source-framed chart labels from table records

Base: `fe3b72336e75992bcfdc9628996083963dbd1596`, branch `feature/pdf-to-excel`.

## Reproduced defect

The pinned public pdfplumber agricultural energy report has a five-column price table beside three separately framed line charts. The whole-page model produced a 44-by-6 grid, putting chart titles, tick values and legend text in 38 cells of the sixth column as though they were fields belonging to the adjacent price records. It also combined one category heading with a Chicago record and treated contact/footer text as records.

This is a data-association correction, not a new Office rendering/layout feature. Source PDF rendering is used as evidence; final Office appearance is not claimed.

## Conservative recovery

The optional retry is limited to one predicted table crossing a unique physical outer frame. Its left data region must consist of cells from that same frame. At least two separate adjacent chart panels must lie within the prediction and frame. Multiple plausible frames, crossing/escaping original model fields, failed evidence or exhausted budgets refuse the contaminated result rather than silently returning it.

Each panel requires an independently detected single-column axis grid, repeated aligned monotonic tick labels, a bounded title, a single category-label baseline and a legend with visible swatches. Every panel token must fit the supported roles. Extra unclassified text, inset ruled tables and borderless summaries are not silently demoted to comments. This deliberately does not support arbitrary chart styles.

At least two substantial monotonic-x polylines per panel must be visible in the final 144dpi raster. Tests cover white, fully transparent and subsequently white/black-covered series. Segment interior points are sampled as well as vertices, so grid-line intersections alone cannot establish visibility. Local contrast is required. The raster is capped at 16MP and sampled pixel reads at 100,000.

The existing region retry then reconstructs only the data area. Every complete native word in that region must have exactly one output owner. Each field's source-ordered string must match, ignoring whitespace only. Source row order and within-row order must agree. Crucially, every column needs repeated independent single-column-cell evidence and globally disjoint source x-bands; a record shifted one column cannot pass merely because all its strings remain present. Text of merged cells must fit the supported column-band span; blank merge extents are not proved. The comparison product is capped at 500,000.

Chart tokens are retained by panel in the first-cell comment, separately from existing source context. Other source-page tokens are retained as explicitly unstructured context. The warning and comment state that these are not record fields, orientation/reading order is not reconstructed, plotted lines are not preserved, and the original PDF must be checked. Context is bounded and never silently truncated. No OCR guesses, model-generated text, numerical rewriting or formulas are introduced.

## Review and tests

Independent review found and drove repairs for invisible-series evidence, same-frame uniqueness, cross-region original-field ownership, adjacent unruled content and comparison-work budgets. A second review found a whole-record column-shift counterexample; global source-column bands now reject it. Final independent review passed 11 focused tests and independently rechecked all 165 nonempty public fields with the new column proof.

Final complete Python suite: 446 tests, 445 passed, one skipped because the external Stirling service is unavailable. The offline layout/OCR model environment was explicitly configured for this run. An earlier run without that configuration failed a scanned-table test and is not presented as successful evidence.

The final frozen-engine public regression completed all 46 PDFs: 42 exported and four remained explicitly refused, with no status changes. Comparing sheet names, dimensions, every nonempty cell coordinate/value/type and merged ranges against the prior outputs found exactly one changed workbook: this agricultural report. The other 41 exported workbooks were unchanged by those checks. All 46 source SHA-256 hashes and all recorded engine fingerprints matched after completion. The corrected report has exactly 42 rows, five columns and 165 nonempty fields matching the independently verified crop at their exact row/column positions. All three chart token sections remain in the source-context comment. No formula elements were found in any generated workbook. Successful export alone is not a claim of source accuracy for the other documents.

## Scope and remaining limits

The supported public report is reconstructed as 42 rows by five columns. Its 165 nonempty fields are proved against native source words and their row/column association. This does not prove every whitespace choice, blank-cell merge, chart meaning or visual equivalence. Graphical lines are not retained; chart text is unstructured reference material, not recovered chart series data. Other chart/table arrangements remain outside this narrow route.

Public-source URLs and hashes are recorded in `scripts/pdf-to-excel/chart-public-manifest.json`; no source PDFs or generated workbooks are committed. All inference and rendering are local. Repository asset checking uses the unmodified checker; it reports 128 baseline approved assets missing from this partial local index, so the repository asset check is not claimed to pass. Remote base-tree publication preserves existing assets. No merge or deployment, no general-production-readiness claim.
