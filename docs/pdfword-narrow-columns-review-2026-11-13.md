# Narrow-column public rendering review, 2026-11-13

Base commit: `2657c160b3a49e98159b9feb96dce1598d55ec97`.

## Reproduced failure and correction

The public W3C OpenOffice two-column PDF has a narrow persistent gutter (left text ends at x302.836, right starts at x306.1). Baseline grouping joined text across this gutter, including a heading and the opposite-column prose. Column reconstruction then failed and LibreOffice rendered the one-page input as two pages. The W3C Word sample's first bullet also split from its text due to baseline interference from the other column.

Native paragraph reconstruction now partitions substantial independently wrapping prose across a persistent central gutter before baseline grouping. Requirements include minimum word/character/line counts, vertical overlap, clear gutter and independently positioned baselines on both sides. Already assigned table cells explicitly disable this partition. DOCX column planning permits narrow gaps only for substantial paragraph/list content with independent baseline evidence.

Independent review found that density alone also admitted long description/definition row tables and would lose their row association. Added independent-baseline evidence and a negative paired-row regression, disabled splitting within native table cells, and restricted the export criterion to prose kinds before publication.

## Final checks

- **99 Python tests passed, zero skipped**; compileall passed.
- Six new synthetic tests cover narrow-column reading order and runs, export column structure, short-grid exclusion, long paired-row exclusion, full-width heading fallback and bullet association.
- Both real public DOCX outputs pass the independent Node OPC check.
- Both outputs render as **one page** in LibreOffice; OpenOffice sample improved from two pages to one.
- Non-whitespace character multisets match source, editable DOCX and rendered PDF for both files. This detects loss/duplication, not semantic reading-order correctness.
- Both rendered pages inspected. Word first bullet is now attached to its text; column content no longer crosses between the two source columns in the OpenOffice sample.
- Unmodified repository guard still reports the same 129 unavailable reviewed assets in this partial checkout; no guard bypass or binary/private input committed.

Public source URLs and SHA-256 values are in `pdfword-public-lists-review-2026-11-13.md`; the same unchanged inputs were used. All PDFs, DOCX files and rendered images stay outside the repository.

## Remaining limitations

This is a bounded two-sample fix, not general release qualification. OpenOffice's wrapped title still has excess paragraph separation, font substitution changes wrapping, and list continuation lines remain separate paragraphs. Full-width spanning headings and ambiguous regularly aligned prose/table layouts keep conservative fallback behavior. Actual Microsoft Word, broader real-document corpus, complete OCR models, full-checkout guard and exact-commit CI gates remain outstanding. No merge or deployment.
