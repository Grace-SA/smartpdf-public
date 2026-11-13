# Irregular record spacing review, 2026-11-13

Base: `deed29bdcdbb0ab260916c8b534f222577aed8e7`.

The preceding blank-record alignment fix required uniformly spaced source baselines. An original synthetic 3-column table with 20/35/25pt record gaps reproduced remaining misassociation: removing a middle value, or values at the leading/trailing edges, moved subsequent values beside the wrong labels.

Removed only the uniform-gap requirement. At least three distinct source baselines, at least two independently shared baselines, matching physical cell row spans and minimum vertical separation remain required. Record positions are retained in source order with explicit blank lines. Spacing is normalized in Word; this does not claim to reproduce the original unequal vertical distances.

Independent review found no blocker, reran all six then-existing cell-line tests and the 113-test suite. Its suggested negative regression was added: one shared baseline does not invent extra record slots. Final suite: **114 passed, zero skipped**; compileall passed.

Real LibreOffice rendering of the original synthetic fixture confirms Alpha→10, Beta→blank/20, Gamma→30/30, Delta→40/blank. Output is editable and passes the independent DOCX package checker. The unchanged public NICS statistical report still converts and renders as one page, passes package checking and retains all non-whitespace source characters in rendered output. Its public URL and checksum are documented in `pdfword-native-cell-lines-review-2026-11-13.md`.

Two additional public pdfplumber corpus files, `senate-expenditures.pdf` and `WARN-Report-for-7-1-2015-to-03-25-2016.pdf`, still require OCR unavailable in this environment. They were evaluated, not counted as successes, and were not modified or committed.

Remaining limitations: arbitrary baseline ambiguity, mismatched font metrics, semantic row subdivision and source-spacing fidelity are not solved. The record-alignment mechanism applies only with independent shared-baseline evidence, not every multiline table. Full real corpus, complete OCR, Microsoft Word and exact-commit CI remain required for release. The unmodified repository guard still reports the same 129 assets missing from this partial checkout. No inputs/output binaries, private data, merge or deployment.
