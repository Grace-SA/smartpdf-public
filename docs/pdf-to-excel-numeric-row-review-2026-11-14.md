# Adjacent numeric-record conflicts: refuse before workbook publication

Base commit: `398b6d1cc3c26657c9ee2a8e9e68b8e121946cce`.
Branch: `feature/pdf-to-excel`. This change does not merge or deploy.

## Independently reproduced defect

The public Camelot `row_span_1.pdf` is pinned by upstream revision, Git blob and
SHA256 in `numeric-row-conflict-public-manifest.json`. Its closed native grid is
40 rows by four columns. The baseline model produces 39 by four and collapses
several footer records. In particular, model cell r37/c3 (zero-based) contains
`25 853`: the visible source's San Francisco / Family Mosaic value `25` belongs
to one row, while `853` is the following Total PHP Enrollment value. An independent
reviewer inspected the actual page-bottom raster and confirmed the separating rule.

There are other defects in this file. The final amount `10,132,875` is mixed with
footer date `12/14/15`, and multiple PCCM text records are joined. This change does
not split or repair those fields, nor claim separate detection of the date issue.
It blocks the overall corrupt export on the narrower proven structural conflict.

## Narrow additional refusal

The existing horizontal rule still requires three distinct model/source rows.
The additional vertical rule only considers closed native grids with at least
20 physical rows, three columns, and 20 numeric native entries. Those counts
limit scope; they do not establish correctness or visibility.

One model cell with rs=cs=1 must own two complete numeric values from two adjacent
native rows in the same column. Both source cells must also have rs=cs=1. Ordered
tokens must match exactly, each source value must have one finite upright
baseline, and the entire glyph set must belong uniquely to that model cell.
Repeating values are located by geometry, not global string matching. Competing
model owners, overlapping native tables, merged source cells, ambiguous strings,
dates, units and fractions do not supply evidence. Four-sided actual-render
contrast for both source cells must establish the shared physical boundary.

This source has a nonzero negative page origin. For the vertical check only,
native geometry stays unchanged; the page bbox origin is subtracted solely when
mapping coordinates into the final rendered bitmap. The horizontal zero-origin
restriction remains unchanged. No PDF content, glyph or value is rewritten.

As with the preceding guard, this is a conservative structural-uncertainty
refusal, not a guarantee of every glyph's visibility, numeric accuracy, or general
table validity. Unsupported evidence retains prior behavior. Each orientation
retains the existing cell, glyph, comparison and render-pixel limits; there are
at most two bounded passes, so aggregate detection work can increase.

## Verification

- Twenty-one local focused tests pass: 11 prior horizontal and 10 vertical tests.
  All 21 were independently rerun successfully. Tests use real generated PDFs,
  including negative origin,
  repeated values, valid model rowspans, source merged/wrapped cells, hidden or
  covered dividers, duplicate owners/grids, reversed order, nonadjacent records,
  small out-of-scope grids, dates/fractions/units and no-mutation checks.
- Independent full conversion of the pinned public source exits 2 with the expected
  structural error. A pre-existing output sentinel retains its exact SHA256.
- Frozen cumulative suite: 502 tests, 501 passed, one external Stirling test
  skipped because that service was not configured (103.888 seconds).
- Frozen 58-PDF public regression: 52 exports and six refusals. The five prior
  refusals remain, and only the pinned row-conflict source is newly refused.
  All 52 remaining exports match baseline cell values/types, number formats,
  style indices, comments, sheet dimensions, merge ranges and row/column sizes.
  Final engine hashes match the complete frozen run. Successful export is not
  an assertion of full cell accuracy for the entire corpus.

## Renderer research boundary

The preceding colored-table recovery investigation remains isolated. PDFium has
font/glyph path and character-origin APIs, but their availability is not proof of
pixel-exact glyph identity. The public glyph-path API performs Unicode-to-character
code mapping ([upstream implementation](https://pdfium.googlesource.com/pdfium/+/refs/heads/chromium/8114/fpdfsdk/fpdf_edittext.cpp)); raw-code correspondence and substituted-font placement still need
verification. Group-level visibility also admits the independently reproduced
counterexample where two overlapping `1` characters render as one `1`. Character
splitting changed actual pixels despite matching extracted positions. None of
those experiments is imported by production or used to relax this refusal.

## Publication limits

Only reviewed text files are published. No public PDF, rendered page, private
sample, dependency binary or font/model weight is added. The partial local index
asset check remains a reported failure; all approved assets are preserved from
the complete remote base tree. CI for the resulting commit must be reported
separately. A blocked wrong export is a safety improvement, not restored coverage
or general launch readiness.
