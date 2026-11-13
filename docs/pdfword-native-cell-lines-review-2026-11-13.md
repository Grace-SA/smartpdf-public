# Public native-table line integrity review, 2026-11-13

Base: `bb983095700de5c1050044bb6efd6860fc760b89`.

## Public inputs and finding

A public federal statistical report exposed a serious content-association problem: native reconstruction found a 17×25 ruled grid, but each tall body cell contained several logical records. Paragraph joining collapsed consecutive state names and numbers into prose, destroying their visible row alignment.

Input: https://raw.githubusercontent.com/jsvine/pdfplumber/stable/tests/pdfs/nics-background-checks-2015-11.pdf
SHA-256: `4f0ae6e017b0e97de211da8fd97316e55bd927af5740d6ce95e1b7b1539f9407`.

Native table cells now preserve physical text lines rather than applying paragraph/heading/list continuation merging. Horizontally separated groups on the same baseline stay on one line. Where neighbouring cells share a regular multi-line record grid, missing record positions are retained as blank lines instead of moving later values beside the wrong label.

Independent review reproduced two defects in the initial implementation: missing record lines shifted values upward, and horizontal groups were treated as separate lines. Both fixed with explicit negative regressions before publication. Reviewer rechecked five tests and the real public table; no remaining blocker in this bounded delta.

## Validation

- **112 Python tests passed, zero skipped**; compileall passed.
- Five new methods verify line retention, editable native table/reopen, preserved blank record slots, same-baseline groups, and no heading/list joining inside cells.
- Public output passes the independent Node DOCX checker and renders as one page in LibreOffice.
- Source, unique DOCX text nodes and rendered PDF non-whitespace character multisets match. Merged-cell aliases are not counted repeatedly in this check.
- Before/after rendering inspected: state names and amounts now remain on separate associated lines rather than collapsed prose. The ruled grid remains 17×25 with multiple records per tall cell, not 50+ separately editable record rows.
- Additional public W3C five-page numbering sample converts and passes DOCX check with five source markers: https://www.w3.org/WAI/WCAG22/working-examples/pdf-page-numbers/page-numbers.pdf ; SHA-256 `a680a8e52b4a9a3df0ed9b45eefb0d116d8b9384d468b662e71a902e7a29f51a`.
- Additional interactive W3C reading-order and Federal Register inputs remain rejected by the existing interactive-content preflight. A public Supreme Court transcript still requires unavailable OCR. These are not counted as successful conversions.
- Unmodified repository guard still reports 129 reviewed assets missing in this partial checkout. Inputs and generated binaries remain outside the repository; no private data committed.

## Limits

Blank-line reconstruction applies only to regular, mutually evidenced baselines with matching physical cell row spans. Arbitrary irregular record spacing and semantic row reconstruction are not solved. Small-font word spacing, table-header semantics, colors and borders differ from source. Character-multiset preservation is not semantic or visual accuracy. Complete corpus, OCR models, actual Microsoft Word, full-checkout guard and exact-commit CI remain release gates. No merge/deployment or general-readiness claim.
