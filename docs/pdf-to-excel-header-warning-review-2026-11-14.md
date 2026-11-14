# Advisory for split parenthesized header phrases

Base: `ccd7c8876611c39b91ea0fbed071cf67f7c252cf`, branch `feature/pdf-to-excel`.

## Evidence and explicit non-repair

The pinned public `health.pdf` in the expanded public manifest exports a title in B1:G1 ending with `(Rs.` and a final H1 value `in 000)`. Source pixels and native word geometry show one complete `(Rs. in 000)` phrase on a common baseline. The gap before the phrase is 31.05pt; internal gaps are 3.89pt and 3.78pt. However, the phrase crosses underlying data columns, the source has no internal first-row divider or structure-tree ownership, and its PDF text object also contains title text. None of this proves that H1 is the correct destination or that the existing merge span is correct.

This change **does not repair the split**, move text, alter numbers, assign a column or change merges. It adds a cautious warning to the conversion result and existing first-cell comment. The warning tells the reader to verify units or headings in the original PDF. It does not copy additional source text into output.

## Detection scope

Only native, unrotated layout tables are eligible. The first row must contain an adjacent multi-column cell ending with an unmatched opening parenthesis and a single-column cell ending with its closing fragment. Both model strings must match complete source words exactly, ignoring whitespace only. Those words must share a baseline and sensible height; the complete parenthesized phrase must be separated from the title by a large source gap and have small internal gaps. The rule does not use currency names, particular words or public sample identities.

This is a deliberately incomplete detector, not a proof of missing units or an exhaustive header audit. A missing warning must not be interpreted as accuracy certification. All previous output values and spans are retained even when the warning fires. Native evidence is not used for scans or hidden OCR layers.

## Verification

Eight focused tests independently reviewed and passed: real rendered synthetic split phrase; complete metadata; ordinary contiguous cross-cell title; independent parentheses; different baselines and genuinely increased source spacing; unsupported/mismatched geometry/text; preservation of workbook cells, merge and existing context; real image-only and hidden-OCR conversion paths with a detector that raises if called.

The nine-file public rerun (six expanded fixtures and three pdfplumber examples) exported all nine. All source hashes and engine fingerprints matched. Comparing sheet names, dimensions, every nonempty cell coordinate/value/type and merged ranges against commit ccd7c88 outputs showed no changes. The only comment change was the intended advisory in health.pdf A1; the other eight workbooks had no comment changes. No formula elements were introduced. This targeted rerun is not a rerun of all 46 public files.

Final complete Python suite: 454 tests, 453 passed and one external Stirling integration skipped. The eight focused tests also passed independently.

The unmodified repository check remains blocked by exactly 128 baseline approved assets missing from the partial local index; no guard was weakened. Remote base-tree publication preserves those assets.

Independent review approved the advisory-only scope. No Office visual equivalence or general production readiness is claimed. Existing GitHub CI and partial-checkout asset limitations remain separate; no merge or deployment.
