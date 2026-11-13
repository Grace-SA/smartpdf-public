# Public PDF native-list coverage review, 2026-11-13

## Scope and finding

Baseline: `86aa4c22d7068f1132686f944789c9f3ced6dcb5`, branch `codex/pdfword-general`.

A real public W3C two-column PDF exported from Word was unnecessarily sent to OCR: the aligned numeric-table guard counted ordered-list markers `2.`, `3.`, `4.` as numeric cells, then treated unrelated text in the other column as table evidence. This blocks conversion where OCR is unavailable and needlessly re-recognizes existing text where it is available.

The guard now exempts only markers with close alphabetic text AND a geometrically aligned wrapped continuation line. Compact numbered-label/status grids remain ambiguous and still require OCR. Baseline-local checks replace the initial whole-page per-marker scan.

Independent code review found that the first implementation's nearby-word-only exemption flattened a numbered-label/status table into column-major prose. It was fixed before publication, with an explicit negative regression. Reviewer rechecked that grid, the public W3C page and synthetic positive/negative tests; no remaining blocking finding in this bounded change.

## Public inputs (retrieved for local validation, not committed)

| File | URL | SHA-256 |
| --- | --- | --- |
| Word two-column | https://www.w3.org/WAI/WCAG22/working-examples/pdf-reading-order/reading-order-2cols-word.pdf | 9a3a38c444fa165d2b33af41fb2c90502c52def5c560f5d543afe01d937d6e80 |
| OpenOffice two-column | https://www.w3.org/WAI/WCAG22/working-examples/pdf-reading-order/reading-order-2cols-oo.pdf | 0c8cd5c891e4b39f85f3f3ebea00c8aa56db35ce1f6d04f1ff263dac43e1ff3a |
| Tagged table | https://www.w3.org/WAI/WCAG21/working-examples/pdf-table-headers/table-example-repaired.pdf | 45defa986c7f576d1243928126ad7dddc5deb915490a4b42d31c963076cffbe6 |
| Simple text | https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf | 3df79d34abbca99308e79cb94461c1893582604d68329a41fd4bec1885e6adb4 |
| Additional encrypted PDF | https://www.orimi.com/pdf-test.pdf | f6edcd8a1b4f7cb85486d0c6777f9174eadbc4d1d0d9e5aeba7132f30b34bc3e |

Four W3C files now convert without OCR. The Word sample previously refused without an OCR worker. Its 26 native blocks / 1,771 text characters retain all non-whitespace source characters in DOCX. Non-whitespace character multisets also match for the other three W3C outputs (an integrity check, not proof of reading-order or layout correctness). The additional encrypted PDF still correctly refuses; no password restriction bypass was added.

## Validation

- Full Python suite: **93 passed, zero skipped**; compileall passed.
- Three new original synthetic regression methods: wrapped numbered lists with dot/parenthesis, compact numbered-label/status grid, and non-list numeric cells. They check native conversion, editable/reopened DOCX, reading order, source immutability and continued OCR refusal for ambiguous cases.
- All four public W3C DOCX outputs pass the independent Node OPC checker.
- All four render in LibreOffice. Word two-column, table and simple text output remain one page. OpenOffice output expands from one to two pages, a remaining pagination limitation.
- Inspected the rendered Word two-column page: columns and text remain present, but the first bullet is on a separate paragraph and line wraps differ. This is **not** a visual-fidelity pass or general release sign-off.
- Unmodified repository guard executed: blocked by the same 129 pre-existing reviewed assets absent from this partial checkout. No guard changes, no user/private data or PDF/generated binaries included.

## Remaining release gates

This is one public-document coverage fix, not a representative accuracy or coverage estimate. Original 139-file private corpus, complete OCR models, real Microsoft Word checks, full-checkout asset guard and passing exact-commit CI remain unavailable/unmet. Compact or unwrapped list/table ambiguities still take OCR. Multiline table/list distinction and bullet/pagination fidelity need further coverage. No merge or deployment is authorized by this report.
