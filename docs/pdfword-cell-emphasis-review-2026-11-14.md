# Native table emphasis preservation

Base: `b694064116f373ab4ab43d287fccf369f9040248` on `codex/pdfword-general`.

## Evidence and change

The pinned public Camelot `row_span_2.pdf` has TimesNewRomanPS-BoldMT labels in both header and body cells. Existing extraction retained their text but export flattened all table typography. Restore bold and italic independently only when all non-whitespace source glyph font names agree on the existing paragraph-style name-marker heuristic. Missing/empty font names skip emphasis. Mixed names with different marker results do not majority-promote a flag. This does not classify headers or infer semantic meaning.

This is a font-name heuristic, not verification of actual font weight or outline shape. Nonempty unknown names without the markers produce false; misleading names and subset names without style labels remain limitations. Mixed-style rich runs and original font families are not reconstructed.

Optional cell flags must be booleans before export. OCR header defaults remain unchanged; explicit false is respected. No changes to source text, values, cell geometry, merges, aligned record padding, paint safety or OCR routing.

## Validation

- Six synthetic tests: four uniform font combinations through real PDF conversion, mixed-cell counterexample, blank/unknown font names, aligned blank records and edit/reopen, OCR header compatibility, malformed flags rejected before writing.
- Full core suite: 167 tests, 164 passed and 3 optional OpenCV scan tests skipped in the core environment. Those 3 scan tests passed separately in the provisioned OCR environment.
- Eighteen public PDFs replayed before/after: statuses identical, 2 converted and 16 refused. Fourteen require an unavailable configured OCR worker, one contains active/embedded content, one is encrypted. This is not an OCR coverage benchmark.
- For both successful documents, complete document.xml is byte-identical after removing only bold/italic run properties. This proves unchanged stored text, numerical strings, line breaks, merges and table/paragraph geometry settings. All 18 source hashes unchanged.
- `row_span_2`: 34 bold run occurrences preserved out of 70 nonempty table run occurrences (merged aliases included); previously all plain. `multiple_tables`: 37 nonempty run occurrences, no added emphasis.
- Independent reviewer ran 23 focused tests and found no content/structure blocker. Review identified the font-name limitation; added an empty/unknown-name regression and documented it explicitly.

## Outstanding acceptance

No Office-rendered visual, pagination or font-metric acceptance is claimed: local LibreOffice conversion currently exits unsuccessfully. This change preserves DOCX style intent, not measured final appearance. The core converter still has major OCR/complex-layout coverage limits; this is not a general-production-readiness claim. Public binaries are not committed. Full repository asset checking remains blocked by 129 baseline allowlisted assets absent from this partial checkout; the unmodified checker is retained. Commit via the existing remote base tree preserves those assets. No merge or deployment.
