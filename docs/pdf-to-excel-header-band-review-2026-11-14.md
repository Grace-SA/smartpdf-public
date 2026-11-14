# Bounded Flate line endings and ruled header-band recovery

## Scope

Feature branch only, based on `47552df16221392209ab72bd6f7cdfb16c90656d`. No merge or deployment. This is a narrow content-integrity correction, not a general production-readiness or OCR-accuracy claim.

Eight additional public PDF/structure-XML pairs (EU013–016 and US013–016) were fixed before conversion and SHA-verified against Camelot commit `92777b852e00933a5c4b9ba642601784604356cd`. Source identities are in `scripts/pdf-to-excel/header-band-public-manifest.json`. Inputs and rendered pages are research-only and are not redistributed here. All eight are native PDFs; this change does not establish new real-scan coverage.

## Verified real defect

EU014 page 2 exported B1 as `(%) indicator in 2006`. The visible source header is `Weight of indicator in 2006`; `(%)` is above the top rule, not inside the header band. The six numerical values and their record associations were already correct.

The source has no outer vertical borders. The evidence is explicitly an open-sided band, not a closed-cell claim: matching full-width top/bottom rules, one continuous internal divider, complete source header glyphs, and at least four independently positioned body records confirming the two logical columns. The output restores the complete header and retains `(%)` verbatim in the A1 comment, explicitly without inferring a column association. Existing page context remains intact.

Independent actual-file verification found only B1's text and source-derived font changed, plus A1's added context. Other values/types, semantic styles, row/column sizes, and merges were unchanged. The source header width is approximately 129.22 pt (Times-Bold metric about 128.80 pt), against approximately 243.03 pt output column width; glyph height is 11.04 pt against 26.19 pt row height. These are geometric/metric checks, not Office-rendered acceptance. Office visual verification was not run.

## Conservative evidence and review fixes

- Only two-column tables with bounded dimensions and unmerged cells are eligible.
- Existing left header and old mixed right header must exactly match their uniquely owned source text; the new right header must have the exact old suffix and a short alphabetic source prefix.
- Only a short parenthesized exterior phrase can be removed from the cell; it is retained in a dedicated comment field. Existing dedicated context causes recovery to decline rather than overwrite data.
- Four complete body records must independently match source text, share each row's baseline across columns, and occupy non-overlapping source bands. Repeating one source frame under several logical rows is rejected.
- Source headers require black upright glyphs, nonempty uniform font identities and consistent heights, no overlapping header glyph boxes, and no intersecting paint/image/annotation evidence.
- Existing bounded final-render contribution verification must succeed. Unsupported clips, Forms, transparency, text rendering modes, and graphics states remain unsupported; they do not grant reconstruction permission.
- Three source rules must be continuously visible in the final render, not merely present as PDF objects.
- Raw character/edge/curve/rectangle/annotation counts, text lengths and comparison estimates are bounded. The 2,000,000 comparison threshold is a bounded estimate, not a claim that every operation is counted dynamically.
- No numeric correction, semantic column guessing, logical-row splitting, or source PDF mutation is performed. If evidence is insufficient, the existing model is returned unchanged.

Independent review initially caught repeated source-row anchors, incomplete resource caps, missing font/height checks, and potential context overwrite. All were corrected and covered by counterexamples before final regression.

## Flate compatibility boundary

The real source's 3,003-byte compressed stream has a complete zlib member producing 8,069 bytes, with `eof=True`, no unconsumed tail, and exactly one unused LF. Previously this caused the optional visibility classifier to decline.

The bounded decoder now permits only `b""`, `b"\n"`, `b"\r"`, or `b"\r\n"` after a complete member. It never parses the suffix as content, attempts a second member, invokes unbounded `get_data()`, or relaxes compressed-input/decoded-output limits. Arbitrary whitespace, trailing garbage, concatenated zlib members, truncation, checksum corruption, and output-budget violations remain rejected. This is limited trailing-line-ending compatibility, not a claim that arbitrary trailing bytes are valid PDF content.

## Tests

Final cumulative suite: **532 tests, 531 passed, one external Stirling integration skipped**, 102.681 seconds.

```
OMP_NUM_THREADS=2 PDF_EXCEL_MODELS="$PWD/excel-models" \
  excel-runtime/bin/python -m unittest discover \
  -s excel-validation/scripts/pdf-to-excel -p 'test_*.py'
```

Independent focused review: **11 header tests + 6 Flate tests passed**. Coverage includes actual rendered white/hidden/covered text, incomplete or white rules, crossing/competing text, duplicated model ownership, repeated source rows, wrong/numeric suffixes, existing context, missing font identity, immutable input, idempotence, and XLSX comment delivery. Decoder tests include exact budget versus overflow, compressed-input bounds, malformed checksum, truncation, chained filters and malicious suffixes.

Frozen public regression: **66 SHA-distinct PDFs, 59 exports, 7 unchanged refusals** (the previous six refusals plus the newly sampled EU015 rotation case). Every frozen engine-file hash was rechecked against the final implementation.

Semantic workbook comparisons against the previous 58-file run and the independent eight-file baseline found exactly two changed cells in EU014: B1's restored text/font and A1's appended unit comment. All other 58 exported workbooks were unchanged in values, types, number formats, comments and semantic styles. All 59 workbooks retained identical row/column dimensions and merge sets. No numerical cell changed.

Verified-manifest evaluation of the eight added samples improves aligned normalized text-and-span matches from 347 to 348 of 592 annotated nonempty cells across 17 tables. Of these, 234 cells belong to the still-refused EU015, and 10 remaining mismatches are EU016 letter-case differences. This is a scoped evaluation, not a population accuracy percentage or an official ICDAR score. Independent positional review distinguished US013's retained in-frame caption from a genuine record-shift error.

Earlier partial experiments and the pre-final 531-test run are not final acceptance evidence.

## Delivery limitations

`node scripts/check-repository.mjs` was run and exits 1 because 128 approved assets are absent from this partial checkout's index. All 128 were independently verified present in the complete remote base tree. Publication uses a reviewed text-file allowlist on that complete tree, preserving these assets; the checker failure is not represented as a pass.

No private documents, source PDFs/XML, rendered pages, dependency binaries, or isolated OCR/rotation research are included. The separate EU015 metadata-rotation experiment is not enabled by this change. Exact-commit CI is checked after push; a failed/unstarted CI run does not establish readiness.
