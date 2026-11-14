# Restore proven body-cell applicability spans, 2026-11-14

Base: `34fd2e54c0dbbfadba4903fd0801b521f4cba618`.

## Reproduced content-structure defect

The public `pr-138-example.pdf` contains two pages of loan-rate tables. In each main table, the Offset column has one closed physical cell spanning all five fixed-term records. Its visible text is `1.50% Partial`. Previously, the workbook placed that text only in L7 without merging L5:L9. The characters were present, but the output incorrectly suggested a narrower applicability range.

Independent source rendering, native physical-grid extraction and workbook inspection confirmed this on both pages. The new output adds L5:L9 and moves the existing text from L7 to L5, preserving it exactly. Every other cell value and merge is unchanged, including the two secondary tables. All existing numeric strings are unchanged. This repairs a demonstrable semantic span, not a claim that the entire document or financial meaning is certified.

Source identities for six newly checked public documents are pinned by upstream commit, Git blob SHA-1 and SHA-256 in `ruled-body-public-manifest.json`. Original PDFs, workbooks and rendered pages are not redistributed.

## Narrow proof, not general inference

A new optional final-adapter step applies only to a single-column, 2–20-row body span in one unambiguous complete closed native grid. Two independent columns must establish each source row's unique model-row correspondence; these rows must be consecutive. This allows the physical body grid to omit model header tiers without assuming a fixed row offset.

The target is exactly one nonempty single-cell prediction whose text equals the native cell after whitespace removal only. Every source glyph must lie completely in the physical cell and visible page, have finite horizontal native geometry, and have its center in that prediction's text bounds. No other model text box may own any of those glyph centers. All other model cells covered by the new span must be absent or explicitly empty single cells. Conflicting text, cross-boundary spans, duplicate owners, malformed geometry, images and annotations prevent recovery.

Every physical side requires real axis-aligned line/rectangle-edge coverage within 2 points of the snapped grid boundary; curve edges cannot complete a missing side and tolerances cannot accumulate beyond that band. This accommodates nearby parallel border strokes already snapped by native grid detection, not missing borders or inferred whitespace. Source-text bounds remain the actual existing prediction bounds, not a fabricated merged-cell rectangle. All other cells and row/column dimensions are preserved; final overlap validation is repeated.

The optional path has explicit glyph/cell, grid, candidate-span, edge-position and cumulative comparison budgets. Ambiguity or malformed evidence returns the original table. It does not replace Unicode characters, invent text, change number strings, insert records or claim visibility proof for arbitrary clipped/overpainted text.

## Review and counterexamples

Initial independent review found curve-assisted boundary completion, stacked boundary tolerances, incomplete model-owner exclusion and nonfinite matrices. These were fixed before integration and covered by counterexamples. Additional tests exercise missing borders, extra native text, conflicting spans, duplicate predictions, only one corroborating column, ambiguous grids, nonmatching Unicode, images/annotations, cropping, resource limits, explicit empty cells and differing native/model header counts.

A real synthetic PDF test injects a faulty model table, runs the final layout adapter and serializes an XLSX, checking the restored merge and unchanged input bytes. Actual public-model execution is separate from that controlled test. No reference annotation enters the converter.

## Remaining limits

This is not generalized nested-table reconstruction, arbitrary borderless row-span inference or production acceptance. Public files with unsupported mixed orientation still refuse safely. Non-table footnotes are not turned into cells merely because they contain numbers. The PPT rendering environment investigation is separate and does not validate this Excel work. No merge or deployment.

The independent reviewer reran all 12 focused tests after the fixes and confirmed the final public workbook differences against the source. Sparse-anchor tests retain valid source boxes while deliberately removing matching evidence; header-offset tests preserve every non-target cell.

Repository validation: the unmodified repository checker was run and remains blocked by 128 existing approved assets missing from this partial checkout index. Only reviewed source/tests/manifests/report text will be committed via a base-tree patch; existing remote assets remain untouched. Exact-commit CI must be checked separately and is not implied by local tests.

Final cumulative suite: **435 tests run, 434 passed, 1 external Stirling integration skipped**. This is the run after the final test additions, not the earlier 434-test run.

All 43 public PDFs were rerun against the final matching engine fingerprints: **39 exported, 4 conservatively refused**. No previous export became a new refusal. Comparing every exported workbook against its saved pre-change version found only the two intended L5:L9 changes; all other values/merges and all nonempty-text multisets are unchanged. Successful export is not proof that every pre-existing defect is fixed.

The original 22-file independent comparison remains unchanged: initial 12 have 2547/2548 whitespace-normalized cell positions and 2546/2548 text-plus-span; next 10 have 934/951 positions and 949/951 row-aligned normalized values.

Final benchmark report SHA-256 values (local evidence, not redistributed):
- plumber: `2d48ca095a7e35f61756b56860d06efd23b0d13b8225645083ee45d3f3472287`
- rotation: `4c4bf406c24265b809e88a69f57ada1cec7d6421639686b5367d456844362503`
- complex: `c77fa0c78b9556f68cca1e059a1398850d6c265ed18bd70c460cbcaaeef0b77b`
- expanded: `48d49e6b88fac5ed1b74d34c1a9ee644f5a2bd44646cf72c563f987b14051760`
- icdar: `f860278c84a2eb2c57f182bea7e75f97519eab6f1b7d2f46f0f6b341883821f4`
- next: `62b829d06a69390df4928e23cb17ffdbb20073cde33d4a8bd02dde5743496297`

Reviewed loan-table output SHA-256: `71237c68b87e36c7f3a960eead145900334d3c1d0dbfe82fa9da27595fc780be`.
