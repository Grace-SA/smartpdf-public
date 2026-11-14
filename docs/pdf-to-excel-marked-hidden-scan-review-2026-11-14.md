# Marked hidden OCR scans: route from final pixels, not stale text

Base: `205028ab2d2815f18afae5776e187d2f2b34c3f2`, `feature/pdf-to-excel`.
This change fixes routing evidence, **not OCR accuracy**. It does not merge,
deploy, change dependencies, enable research adapters or increase budgets.

## Independently acquired paper scans

Two small historical US Census publications were obtained from the official
Census archive. Original document URLs, selected pages and hashes are recorded
in the accompanying manifest. Both are historical US federal publications;
no source PDFs, images or generated workbooks are redistributed here.
The selected-page PDFs preserve page content and were pixel-equal to the
original pages at 144 dpi. They are not fresh rasterizations of modern PDFs.

* Bulletin 57 (1901), PDF page 2: a worn, two-panel state-area table with a
  contradictory old OCR layer. An independent image-only annotation covers
  Alabama through Georgia, explicitly a partial table. Three uncertain printed
  numerals were excluded pending a second visual interpretation.
* A Century of Population Growth (1909), the linked part07 PDF page 13,
  printed page 92: a pure-image page. The lower-right apportionment table has
  an independent image-only annotation of 12 records and seven columns.
  The official section label does not accurately describe the file contents;
  page selection is bound to the actual PDF and hash.

The first page has 433 nonempty text-show operations, all explicitly `Tr=3`,
301 balanced `/Suspect << /Conf 0 >>` marked-content pairs, and one image
covering the nonzero CropBox. The old classifier declined its vector lines,
clipping and confidence metadata. Conversion consequently treated the stale
invisible layer as native text, producing malformed and incorrect numbers.

## Narrow proof and final-render-only routing

The classifier now permits only `/Suspect` with exactly one finite numeric
`/Conf` property in [0,1]. Tags must be names, marks must balance, and nesting
is bounded. Optional content, ActualText, named property resources, unknown
graphics states and other unknown operators still decline classification.

On the page only, finite line/rectangle paths, strokes, `W*` clipping and
nonnegative line widths are accepted under a bounded syntax check. They cannot
make `Tr=3` text paint. Every nonempty text show must still be hidden; mixed
visible text is not discarded. The existing restricted identity, text-only
Form support and its state isolation remain; paths inside Forms are not added.
A single image may fully cover the CropBox rather than match it exactly.
Existing near-equality tolerance is retained, not enlarged.

This evidence authorizes **only ignoring the invisible text layer**. The caller
renders the final PDF, including every supported cover and clip, before OCR.
It never substitutes the embedded image, restores hidden values, guesses
numbers, or uses reference labels to correct recognition. Disabling OCR or an
OCR failure refuses output rather than falling back to the hidden layer.

## Accuracy limitations are material

On 28 confidently annotated numeric cells in the partial 1901 table, the
baseline matched 21; final-pixel OCR matched 24. Four numeric errors remain,
including **two regressions**: Delaware water area `90` became `06`, and Georgia
land area `58,980` became `58,080`. Alaska and California also remain incorrect.
Three uncertain cells, all labels and the unannotated remainder are outside
this denominator. This is not a population accuracy estimate or a claim that
recognition is safe for unattended numeric use. The route emits the existing
explicit OCR warning. The 1909 table still has substantial recognition omissions.

Six additional fixed cTDaR document images were also inspected. Their physical
scan provenance is not established, so they are not counted as acquired paper
scans. All six exported, but examples include omitted dash placeholders,
`139.1` recognized as `1661`, and `19.78` as `10.78`. No sample-specific numeric
repair or relaxation was made. These are unresolved release-quality defects.

## Verification scope

Eight new focused tests cover crop coverage, q/Q and cross-stream text state,
mixed visible shows, text clipping modes, malformed/unknown metadata, bounded
paths, and final-page covers/clips. Two covered/clipped fixtures are verified
white by a renderer and then passed through real conversion (PDFium and
RapidOCR), which refuses without producing a workbook. A contradictory hidden
`19.50` fixture yields only the visible `12.50` in an actual OCR conversion;
OCR-disabled and injected-error paths produce no workbook.

A before/after classifier inventory covers 93 distinct local corpus PDFs,
269 pages, including public files and controlled scan simulations. Only the
1901 selected page changes decision; the other 92 PDFs have identical decision
lists. This is **classifier regression**, not 93 new end-to-end conversions.
Final frozen tests and the two acquired-scan conversion results are recorded
in the manifest. Models, source strings, time/pixel limits and all other engine
modules are unchanged. Independent review checked the hidden-mode evidence and
adversarial tests. No Office-rendered workbook or general launch acceptance.
The inherited local asset checker remains blocked by 128 missing approved
assets in the partial checkout; remote-tree publication preserves them.
