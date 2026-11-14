# Source-dimension matching for supported full-page scans

Base: `16f93c5161aef440012b380e3650d9e7dae70deb`, branch `feature/pdf-to-excel`.

## Reproduced integrity problem

Six additional pinned Camelot public documents exported successfully. Directed independent checks matched 136 District Health and 216 Population Growth values; another directed check matched 300 Superscript fields. Rainfall Distribution matched its native physical grids. Export success is not an accuracy estimate. The two unit/header-association defects found in this pass remain unresolved: a full-width rule alone cannot distinguish external metadata from legitimate upper-level headers, so speculative relocation was not shipped.

Three of those real public documents were rendered at 150dpi and embedded as single-image PDFs without native text. These are controlled scan simulations, **not independently acquired real scans**. On the rainfall simulation the fixed 144dpi raster lost thin lines that existed in the embedded image. This caused a 43-by-10 main table to become 39-by-9 and an eight-row summary to become five rows, including loss of the Excess / 12 / 5 record. Pixel probes verified missing lines became white, so merely changing a binarization threshold could not restore them.

A fixed increase to 216 or 288dpi was investigated but not adopted: both improved geometry yet introduced different recognition errors. The chosen route instead matches the source scan's dimensions when that can be narrowly verified. It is not a claim that higher DPI always improves recognition.

## Conservative implementation

Only one full-page image is eligible, with an unrotated, uncropped, zero-origin page and a jointly satisfiable native raster-size interval between 144 and 300dpi. A bounded content-stream inspection verifies exactly one invoked image, positive axis-aligned page-size transform, no translation/shear/mirroring, and matching image dimensions. Forms, explicit clipping, text-clipping render modes, graphics-state changes, masks, annotations and nondefault UserUnit decline the optimization. The existing 144dpi route remains available otherwise.

The final PDF is always rendered, including subsequent opaque drawing. The embedded image is **never** substituted for the final page. This preserves covers/redactions rather than bypassing them. Native-size agreement alone is not described as universal proof of unchanged sampling. One controlled fixture additionally verifies pixel-for-pixel equality without an overlay; another verifies a full opaque cover remains blank.

Predicted raster dimensions use ceiling on both axes. The 20M-pixel cap is checked before rendering and against the actual result before OCR. A candidate rendering with unexpected dimensions is discarded and retried at 144dpi with fresh budget checks. The OCR engine receives only the final chosen raster.

The scan-grid path now converts raster sizes back to PDF units using its actual selected scale. Morphology minima, grouping distance, contour minima, border/merge probes and text-line bucket sizes are scaled from the same existing physical thresholds. No recognised text is corrected by expected values, sequence completion, public reference labels or numerical guesses. The model/leader paths are not rewritten.

## Evidence and review

The candidate restores both rainfall grids to 43-by-10 and 8-by-3. All seven merged ranges match the source physical grid. Of 411 nonempty source cells, 409 match exactly after whitespace normalization. The summary's 23 fields all match, including the previously missing Excess / 12 / 5. Remaining errors are a duplicated W in NORTH WEST and an omitted row serial 3. They are not guessed or silently declared correct. The other two scan simulations have unchanged workbook cell values; independent checks confirm their 216 and 136 numerical/NA fields, not perfect labels or footnote typography.

Independent review approved 12 focused tests: source dimensions and a pixel-equal fixture; 100/150/200/300/301dpi eligibility; mirror/shear/subpixel offset and incompatible aspect; multiple images/transparency; rotated/cropped pages; opaque final-page cover; over-budget native dimensions; ceiling-sensitive pre-render budget; physical grid dimensions; legacy route; unexpected-size 144dpi retry; and actual-render budget rejection before OCR.

Final frozen Python suite: 466 tests, 465 passed and one external Stirling integration skipped.

Final frozen targeted regression: 12/12 exported (nine existing public documents plus the three controlled scan simulations). Source SHA-256 and all engine fingerprints matched after completion. Comparing sheet names, dimensions, every nonempty value/type/position, merge ranges and comments against prior outputs found only the intended rainfall scan workbook changed. The other 11 outputs matched by those checks. The final rainfall output independently reconfirmed 409/411 exact nonempty source fields and all seven merge ranges. No formula elements were introduced. This is a targeted regression, not a rerun of the full public corpus or a population accuracy claim. An earlier exploratory run changed while review was in progress and is not substituted for this frozen result.

The unmodified repository asset checker reports 128 baseline approved assets missing from the partial local index; it is not claimed to pass and no guard is relaxed. Remote base-tree publication preserves those assets. No public PDF or generated workbook is committed. Source URLs/hashes and the scan-simulation protocol are in `scripts/pdf-to-excel/scan-raster-public-manifest.json`. No merge, deployment, Office visual acceptance or general-production-readiness claim.
