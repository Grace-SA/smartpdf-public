# Repeated numeric-column conflict: fail closed, no reconstruction

## Source and independent diagnosis

Base: `00673c1509d42ca1ab3462b2f18e515dfc4e5a7f` on `feature/pdf-to-excel`.
The companion `numeric-conflict-public-manifest.json` pins the public Camelot
sample `column_span_1.pdf` to its upstream revision and SHA256. No PDF, rendered
page, private input, model weight or dependency binary is added by this change.

The visible source has eight columns. Native geometry gives 50 rows excluding
the page title; the baseline model gives 51 rows including that title but only
seven columns. All 47 annual records lose the separation between Accidental
Deaths Rate and Suicides Incidence. Four affected rows also demonstrate
cross-record contamination: 2006's `118112` is included in the 2005 record, and
2010's `32.4` is included in the 2011 record. The other 43 records concatenate
the two source fields (the first additionally includes the `(6)` column index).

An independent reviewer inspected the source raster and physical boundaries,
compared the records, and reproduced the defect. Excluding the title, the
baseline's non-whitespace character multiset exactly matches native extraction.
Thus character conservation alone does not prove correct table structure.

## Deliberate safety decision

This change **refuses the incompatible extraction**, not reconstructs the table.
The source uses ICCBased purple/blue text and a reverse-text title. The existing
black-glyph visibility proof cannot establish safe colored/reverse-text recovery.
Neither a character multiset nor numerical plausibility authorizes reassigning
values. Colored glyph recovery remains disabled/unimplemented.

The new bounded guard requires at least three distinct source rows and three
distinct model rows where the same model column joins two adjacent, individually
closed native numeric columns. It requires exact ordered tokens, complete glyph
ownership within the model box, one upright finite baseline, no competing model
owner and no overlapping/nested native table. Source merged cells, multi-line
numbers, ambiguous numeric strings and fewer than three observations do not
provide this evidence. Repeated values are matched by geometry, not string search.
Final 144-dpi rendered contrast establishes all four physical sides of each cell;
invisible and subsequently covered dividers do not establish the boundary.

**This is an uncertainty/refusal check, not a proof every native glyph is visible.**
Transparent or reverse glyphs do not authorize reconstruction; repeated structural
conflicts may still conservatively refuse. No text or native value is copied into
an output, no PDF content is changed, and no rule claims numerical OCR accuracy.
The refusal occurs before workbook writing, with existing output files preserved.

Bounds include 300 rows, 30 columns, 9,000 model cells, 50,000 nonspace glyphs,
100 native tables, bounded comparison products, and 20 million render pixels.
Unsupported/malformed evidence and render errors retain the prior behavior,
not a universal rejection. Detection therefore is not a comprehensive validator.

## Review and tests

The independent reviewer found a nonfinite glyph-matrix loophole in the initial
prototype: NaN comparisons could admit invalid baseline evidence. The final guard
checks all six finite matrix entries, upright positive axes, negligible shear,
and integer model indices/ranges. Actual PDF merged-cell and wrapped-numeric
counterexamples were added rather than only changing model strings.

- Eleven focused synthetic tests pass, independently rerun. They cover repeated
  values, legal separate columns, real merged/wrapped source cells, insufficient
  evidence, duplicate native tables, repeated model rows, token order, malformed
  geometry, render failure, invisible/covered boundaries, and transparent/reverse
  text conservative refusal. They are not an exhaustive PDF graphics suite.
- Independent full conversion of the pinned public PDF exits 2 with the expected
  conflict error; a pre-existing destination sentinel retains its exact SHA256.
- Frozen final cumulative suite: 492 tests, 491 passed and one external Stirling
  integration skipped (100.825 seconds). The external service was not configured;
  that skipped test is not counted as passed.
- Frozen 58-PDF public corpus: 53 exports, five refusals. Four prior refusals
  remain unchanged (two unsupported rotations, nested label reversal, Senate
  rotated tables); the only new refusal is the pinned numeric-conflict case.
  All 53 remaining exports match baseline cell values, types, number formats,
  style indices, comments, sheet dimensions and merge ranges. Four row/column
  size differences occur in two documents, maximum absolute difference
  0.00006103515625; these are reported rather than claimed byte-identical.
  Export success is not a claim that every cell in those files is correct.
  Final engine fingerprints match the complete frozen run.

## Verification limits and release status

This does not restore conversion coverage; it replaces a known silently corrupt
export with an explicit refusal. Other source layouts and fewer/isolated mixed
records can remain undetected. Recovery needs a broader final-render per-glyph
visibility and source-ownership proof, particularly for color spaces, clipping,
transparency and reverse text. No thresholds were relaxed to increase exports.

The repository asset check reports approved assets absent from this partial local
index. Publication preserves the complete remote base tree and changes only the
reviewed text-file whitelist; no missing assets are deleted or replaced. CI must
be checked for the resulting exact commit. This branch change does not merge,
deploy, enable experimental OCR, or establish general production readiness.
