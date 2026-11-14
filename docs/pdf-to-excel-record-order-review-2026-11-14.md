# Source-record order conflict refusal

## Scope

Feature branch only, based on `0441f3977579884467c4fae4655e084a6abbddf8`. This is a narrow structural refusal, not a record reconstruction, a general visibility certificate, a production release, or new rotation admission.

A fixed expansion of eight public PDFs (EU017–020 and US017–020) was selected before conversion from `camelot-dev/camelot` commit `92777b852e00933a5c4b9ba642601784604356cd`, under `tests/files/tabula/icdar2013-dataset/competition-dataset-{eu,us}`. All 16 PDF/XML Git blobs were verified and the eight PDF SHA-256s differ from the earlier 66-file corpus. Source PDFs, XML, screenshots, generated workbooks and dependency binaries are not published here.

Independent source-image and workbook review found a serious error in US019 page 2, Table A1: separately displayed population and economic assumptions were folded into large cells, a percentage was stranded in another row, and the `Population` label appeared after later age-group labels inside the output cell. Merely retaining most strings did not preserve their record associations. Other source tables and neighboring corpus cases must not be used to excuse this error.

## Refusal evidence

The check runs only on existing native, non-OCR layout tables, before the atomic workbook writer. It does not split, insert, correct or move any value.

The bounded eligible subset has two columns, a long left-column model cell, and four to six independent whole PDF text-show operations. Each operation must contain two separated, horizontal, same-baseline text groups; the left strings are unique and already present in the same model cell. The group needs at least three distinct right strings and at least three digit-containing right records, already represented in output. Source rows must have consistent left/right alignment and bounded vertical gaps. The left strings must appear in a different order inside the model cell than their top-to-bottom source order. Ordinary paragraph wrapping in unchanged order is not enough to trigger the check.

Every source glyph in both groups is checked against all model cells with valid source rectangles, including empty cells. The left owner must uniquely be the candidate; the right owner must uniquely be a single right-column cell. An overlapping partial owner declines that record. The number of complete right-string occurrences in the owner must equal the number of exclusively owned source records using that string; another row's repeated value cannot be borrowed as corroboration. In US019, the age-group record with the independently stranded percentage is excluded due to competing ownership. Four other records still establish the ordering conflict.

## Named-color and rendering boundary

A dedicated helper supports this refusal only. Existing recovery helpers and their black-glyph restrictions are unchanged.

It compares PDFMiner's original text-show byte/number sequences against bounded pypdf operations, and matches the complete glyph text/geometry multiset against the existing page extraction. It rejects duplicate coincident glyph identities, Forms, images, clipping operators, nonzero source text-rendering modes, transparency groups, non-opaque/blended/overprint states and unsupported operations. Positive uniform page scale operations are permitted; the selected glyphs still require horizontal, positive matrices. Text knockout and stroke adjustment are accepted only in their explicitly checked true states.

Named color support is not keyed to a PANTONE name. It is restricted to bounded Separation spaces using an explicit Type 2 tint function with checked dimensions, domain, ranges, endpoints and exponent. Alternate spaces are supported Device spaces or checked ICC profiles: maximum one MiB, consistent declared size/channel signature, at most 64 tags with in-bounds extents, no external streams or unsupported dictionary entries. This validates the bounded input shape, not ICC colorimetric accuracy.

The untouched copied page must render exactly equal to the original RGB page. For each selected whole text show, temporary `Tr=3` / `Tr=0` wrappers suppress only its painting while retaining text advancement. Each candidate glyph rectangle must contain at least two changed pixels, and all changes must remain within the selected show's padded glyph rectangles. No modified PDF is used for conversion or published.

**Limited contribution is not proof that every glyph is fully visible or correctly decoded.** Bounded kerning overlap within a show is allowed; unrelated-show overlap is not. The evidence supports a conservative refusal of uncertain record ordering only. It must not authorize field recovery, new conversions, color fidelity, or general concealed-content protection. Unsupported/ambiguous evidence declines this optional check and is not a declaration that the existing conversion is safe.

## Resource and output bounds

Limits include 10,000 glyphs, 500 shows, two candidate cells, a cumulative two-million comparison budget, at most six distinct target shows with cached results, three-million pixels per bitmap, a cumulative 21-million rendered pixels including the original page, 40 MiB per serialization and 80 MiB cumulative serialization. Existing document/page/cell limits remain unchanged. Exceptions in optional evidence decline the check; a verified conflict becomes an explicit conversion error before output publication.

## Verification

Focused generated fixtures cover normal and named-color text, generated ICC data and malformed profile bounds, reverse text, normal source order, separately represented records, white cover, clipping, transparency, overprint, Forms, coincident duplicate shows, wrong/competing/cross-column right owners, missing duplicate-string occurrences, left geometry competition including empty cells, rendering-copy mismatch, raw-show identity mismatch, unchanged input/model data, restored input-stream position, and target caching/budgets.

Two integration tests use a deliberately conflicting model double at the structure-model boundary. They verify the real conversion/output path preserves an existing output byte-for-byte or creates no new output. They are not described as independent-model end-to-end tests. Separately, the actual bundled models on public US019 page 2 produce the problematic table and now receive the explicit refusal; the full-document corpus run checks the complete file.

Final frozen suite: 557 tests, 556 passed and one external Stirling-service test skipped, in 102.054 seconds. Independent final review also ran all 16 focused/integration checks successfully (14 focused and two model-boundary integration tests).

The frozen 74-file corpus produced 65 exports and nine refusals. Compared with the previous 66-file run plus the fixed eight-file expansion, the sole status change is US019: its full document now receives the explicit record-order refusal instead of the erroneous workbook. No other file gained or lost export coverage. Every recorded engine SHA-256 matches the final tested source.

Across all 65 retained workbooks, cell values, types, number formats, comments and resolved semantic styles are identical to their baselines; merge sets are identical. One file (`chart-final__next__us-010`) has three small dimension differences: two row heights increased by 0.00006103515625 pt each, and column A width increased by 0.0000029064360163 Excel column-width units. All other dimensions match exactly. These differences are recorded, not rounded away or described as exact layout equality. No new Office-rendered visual claim is made.

The verified 16-reference subset has 3,066 normalized, row-aligned text matches out of 5,860 annotated nonempty cells. Its reduction by 361 matches from the combined baseline is explained by deliberately refusing US019 rather than exporting its erroneous associations. This is not a population accuracy rate. Successful exports elsewhere are not an accuracy claim. The US017 caption/group-header defects and EU015 rotation refusal remain unresolved; this change does not repair them.

The local repository checker cannot pass because this partial checkout index lacks 128 approved assets. Publication must use the complete remote base tree and preserve every asset, changing only the seven reviewed text files. Exact-commit CI must be checked after pushing; failed/unstarted jobs are not passing CI. No merge or deployment is authorized.
