# Mixed wrapped/unwrapped native agendas

Base: `9e160fdada5d6e06e3c7c22540592f762703257a`, branch `codex/pdfword-general`.

## Evidence and narrow repair

The pinned public pdfplumber `cupertino_usd_4-6-16.pdf` passes native paint safety but its six consecutive main agenda markers trigger the aligned-number/table guard. The old list exception requires a nearby continuation for each individual marker; several real agenda items are standalone headings, and marker-to-heading spacing exceeds the old 12pt limit.

Recognize one complete, geometrically consistent agenda sequence only: at least three consecutive positive integer markers with matching punctuation; stable marker and heading origins; heading gaps bounded by glyph height; no independent heading columns. At least two different items need an immediately adjacent, same-indent prose continuation of six words and forty non-space characters. These conservative thresholds are evidence filters, not semantic understanding.

Check every intervening item line for the same prose column, not only heading baselines. Do not choose a valid prefix/subsequence from duplicated, skipped or reordered numbering. Isolated punctuation remains in output but is not evidence. Nested decimals and regulatory numbers are neither promoted to main markers nor rewritten. Only exact proven source word objects are excluded from aligned-number counting. Existing paint, sparse-grid, table, preflight and OCR gates are unchanged. Ordinary two-column lists continue to use the previous independently tested route.

## Validation

- Four new synthetic test methods cover full conversion/edit-save-reopen and exact headings; no wrapped items, only one wrapped item, two continuations of the same item, duplicate/skipped/reordered/mixed-punctuation numbers, independent heading/status columns, incorrect continuation indent, nested labels and isolated source punctuation.
- Full core suite: 177 tests, 174 passed and 3 optional OpenCV scan tests skipped. The three scan tests also pass in the provisioned OCR runtime.
- Independent reviewer ran 13 agenda/list/indexed-register tests, found no blocking issue, and separately compared the public agenda body: its full 1,181 non-whitespace character sequence from first main item through last item is unchanged.
- Public replay: only this agenda changes from refused to converted. Success count is now 4/18; the three previously supported documents have byte-identical document.xml. All source hashes unchanged. Fourteen still refuse (twelve needing a configured OCR worker, one encrypted file and one active-content file).
- All native characters outside existing raster regions match the DOCX character multiset. Both embedded PNGs equal independently rendered source crops pixel-for-pixel. All 1,122 non-whitespace characters assigned to the boxed notice lie wholly inside its source crop; none straddle its boundary.

## Important fidelity limits

The existing graphics path retains the logo and boxed introductory notice as two images. The notice's 1,122 characters are visually retained, not editable text. This patch does not claim whole-page editable recovery. The six-item agenda body, nested labels and numbers are editable and ordered correctly. Source-crop pixel comparison is not final Word/LibreOffice pagination or visual acceptance; local LibreOffice conversion remains blocked.

Full unmodified repository checking remains blocked by 129 baseline approved assets missing from this partial local checkout. Remote base-tree commit preserves those assets. No source PDFs, generated DOCX or private samples are committed. This is not general production readiness; no merge or deployment.
