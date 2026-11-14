# Reunite one-line source-backed label fragments without changing numeric fields

Base: `1209386126440dfdac22126f915418561fafaf42` on `feature/pdf-to-excel`.

## Public-source correction

The pinned Camelot `diesel_engines.pdf`, page 11, contains the complete label
`Turbocharger lubricating oil inlet pressure` in one closed physical cell. The
baseline workbook incorrectly separates the last word into a second column.
The new recovery joins the existing A12 and B12 strings with their actual source
space and creates only merge A12:B12. It does not delete or resize a global column.
The sheet remains 28 by nine; other numeric and text fields retain their positions.
The companion public manifest records upstream revision, Git blob and SHA256.

This is an actual editable-field correction, not another refusal. It is also not
complete table recovery: existing mixed `L LL` subrows and other interpretation
limitations remain. It does not establish broad production readiness.

## Conservative evidence

Only adjacent single-row/single-column ASCII label fragments can join. Digits and punctuation other than internal hyphens are excluded, as are
hyphen-ending fragments. A
unique closed, unmerged native cell must contain exactly the two complete existing
strings in the same order. The entire glyph set must have one upright baseline,
black opaque appearance, uniform source font/size and unique model ownership, without glyph overlap beyond
the existing narrow kerning allowance. A third owner, duplicate native table,
occupied span, or ambiguous chain prevents recovery.

The joining boundary requires one actual ASCII space glyph with the same source
font, matching adjacent glyph extents and a normal bounded width. Neither a large
blank interval nor whitespace-stripped character equality establishes a join.
The complete extracted source string must exactly equal left text + one space +
right text. No native text absent from those two model cells is added.

Existing visibility protection remains: unsupported clipping, transparency,
Forms and graphic states decline; intersecting strokes/fills, images and annotations
cannot establish evidence. Both native physical sides and final-render boundary
contrast must agree. The existing bounded text-contribution renderer must also
verify candidate glyph contribution. No source PDF is edited, and colored-table
experiments do not enter this path. Work, glyph, edge, cell and rendering limits
apply; raw edge/curve counts are capped in addition to filtered physical edges.

The result deep-copies the model and changes only the two target entries into one
span. Row/column dimensions are not assigned by this recovery. The former cell
string multiset necessarily changes; the accurate invariant is preservation of
ordered source words/characters and all other fields, not an unchanged cell Counter.

## Independent review and tests

Thirteen focused tests pass and were independently rerun on the final code. Real generated PDF cases
include large word spacing, different baselines, mixed-font emphasis, and a white stroke painted directly
through the candidate label. Other checks cover hidden/white text, clipping,
transparent/invisible borders, overprints, absence of a literal space, reversed or
truncated fragments, hyphen/punctuation/numeric fragments, overlapping spans,
third owners, duplicate source tables, render exceptions and idempotence.

Independent end-to-end conversion of the public page changes only A12/B12 values
and adds A12:B12 to the existing merges. Other values, types, coordinates, actual
style properties and row heights match the baseline. Single-page runs produce
workbook-local style IDs different from full-document runs; semantic font/fill/
border/alignment properties were compared rather than treating IDs as formatting.
A tiny A-column width difference between inference runs was recorded:
20.95028639748419 versus 20.95027949469866 (about 0.0000069028). No other column
width differs in that focused comparison. This is not an Office visual-render
acceptance test or a claim of byte-identical workbooks.

Frozen final cumulative suite: 515 tests, 514 passed, one external Stirling test
skipped because the service was not configured (99.433 seconds). The final
58-PDF frozen public regression completed with 52 exports and the same six
refusals. All 51 other exports match baseline values/types, number formats, style
indices, comments, sheet dimensions and merge ranges. One unrelated header-row
height differs by 0.0000305175781321 in a separate inference run; no other
row/column sizes differ. The full diesel workbook changes only the two target
cell values and adds A12:B12; B12 becomes a merged placeholder, with its
corresponding type/style change. All other actual cell styles and numeric values
are unchanged. In this full-document comparison, diesel row/column sizes match
exactly. Final engine hashes match the complete run. Exports are not scored as
universally correct merely because they completed.

## Publication and limits

Only reviewed text source, synthetic tests, a public source manifest and this
report are published. No PDFs, rendered pages, private inputs, dependency binaries
or model weights enter Git. The local partial-index asset check is a recorded
failure; publication preserves the entire remote asset tree. CI for the exact
commit must be checked separately. No merge, deployment, experimental OCR enablement
or colored/rotated-table recovery is authorized by this change.
