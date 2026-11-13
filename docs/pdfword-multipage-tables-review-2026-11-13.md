# PDF to Word: semantic multipage table headers

Base: `613cdf591de120bd8d592b4d602f64c8db4def3f`; feature branch `codex/pdfword-general`.

## Core correction

The previous continuation detector compared only the text of the first row. Two separate tables with identical first data rows near adjacent page edges could be combined and one data row discarded. A reproducible two-page synthetic example retained only one occurrence of `12.34`, instead of both source occurrences.

Continuation now distinguishes complete semantic header rows from data rows. Header identity includes all leading header rows, cell positions, merge spans and exact trimmed text, not just first-row labels. Ordinary repeated data is never removed as a header. Explicit continuations without proven repeated headers preserve all rows.

Two-level headers, including a row-spanning label and grouped column headings, now remain one editable table across continued pages. All leading header rows are marked for repetition by Word, and only the matched complete header prefix is skipped. `thead` establishes header semantics even when its cells use `td`. Header-only follow-ups, changed second-level headings, changed merges and spans crossing into the body are handled conservatively without discarding content. Export independently refuses stale skip metadata that would remove data rows.

## Evidence

- **75 PDF-to-Word Python tests passed, zero skips**. Eleven new tests cover duplicate native-PDF data, explicit continuations, two-level merged headers, changed header labels/structure, semantic `thead`, unsafe spans, header-only follow-ups and malformed skip metadata.
- The two-page native synthetic PDF test converts without OCR and preserves both first data rows and distinct second data rows.
- Paired unchanged-source probes: duplicate-data output changed from one table/three rows/one `12.34` occurrence to two tables/four rows/two occurrences. A two-level continuation changed from two separate tables/six rows to one table/four rows, preserving both unique data rows.
- Independent DOCX package validation passed for both paired outputs with two source-page markers each. Edit/save/reopen, merged ownership and marker preservation are tested directly.
- LibreOffice independently rendered the duplicate-data example to two pages and the short merged continuation to one page. Source-page markers identify provenance, not a promise of identical output pagination. Rendered text and visual inspection confirmed the amounts, merged headers and distinct data survived.
- An 80-record synthetic continued table rendered to two pages. All 80 record labels were retained, and both header rows appeared on both pages. The second rendered page was visually inspected.
- Independent code review exercised a three-page continuation, preserving all three unique data rows and all three markers. Its additional defensive finding about stale skip metadata was fixed and regression-tested.

## Remaining acceptance limits

No whole-corpus coverage or accuracy percentage is updated by these synthetic tests. Native headers lacking reliable semantic evidence remain separate tables unless explicit continuation evidence exists. This favors preserving all source data over speculative deduplication.

The original private corpus, original OCR model environment and actual Microsoft Word are unavailable in this cloud workspace. Full-site/browser regression, production capacity and exact-commit successful CI remain outstanding. The unchanged repository guard was run against the partial index and still reports 129 existing approved assets absent; it is not claimed to pass. Publication preserves the original remote tree and unrelated binary objects. No private samples or rendered outputs are published, and no merge or deployment is performed.

General production readiness remains false. This change fixes reproducible common multipage-table content loss and improves editable multirow headers; it does not establish general table recognition accuracy.
