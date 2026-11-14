# Reject unresolved dominant native text rotation, 2026-11-14

Base: `f1f1671ec7bd068c6bba5ca15ebcd71b9ad6ab55`.

## Reproduced content-integrity defect

A second fixed six-file public set covers multiple tables, nested tables, column/row spans, vertical headers and content-stream rotation. Inputs are pinned in `complex-public-manifest.json`. All six initially exported, which did not mean correct conversion.

In anticlockwise_table_2, PDF page Rotate is zero, while 2276 of 2278 visible nonempty glyphs have a sideways baseline. Two upright footer glyphs prevent the existing unanimous-orientation recovery from admitting the page. It nevertheless entered horizontal table reconstruction and produced a misleading 17-by-6 workbook, concatenating multiple records' numeric strings and footnote text into cells. Independent source/output review reproduced this failure.

## Narrow fail-closed repair

Before forms or model/native table reconstruction, selected native pages with zero page Rotate metadata are now rejected when they have at least 20 visible nonempty glyphs and at least 90 percent share one nonzero exact quarter-turn direction. This threshold authorizes refusal, never majority-vote rotation, glyph movement, value repair or guessing. It covers dominant sideways and upside-down content in the ordinary native/model path, where zero page Rotate metadata previously bypassed the rotation checks. Original PDF and any previous workbook remain unchanged on refusal.

The existing unanimous-orientation recovery remains in place; supported metadata-rotated pages still normalize and convert. Independent review caught an initial broader guard that could also preempt the existing Stirling route. The final condition preserves unhandled nonzero-Rotate pages for that route; a mocked fallback test verifies it is reached without making a network call. Proven hidden-OCR image pages keep their separate OCR path. Ordinary horizontal table bodies with some rotated headings are outside this narrow new refusal. The public vertical_header counterexample has 236 of 1074 non-upright glyphs, not a dominant sideways body.

Below-threshold, small, skewed, mixed-direction and vertical-writing documents are not declared correct. Legitimate predominantly vertical designs may now be conservatively refused. This is fewer silently corrupt successful exports, not expanded orientation support or higher OCR accuracy. An upright-content source is required; changing only page Rotate metadata is not promised to resolve every mixed-direction document.

## Independent review and regressions

The target-character/font experiment was not forced into production: its visible-glyph and exact-character-preservation evidence remains insufficient. The new repair instead addresses independently reproduced table corruption without replacing any characters.

Rotation regressions cover the 90-percent/minimum-size boundary, upside-down and both sideways directions, mixed quarter-turns, malformed matrices, ordinary vertical headings, unchanged original/output files, and proof that the model is never called for the unsafe native page. Existing metadata-rotation, crop and raster comparisons remain applicable.

Known complex-set residual: tableception retains its 12 nested numeric cells but splits an outer disease/status record and reverses a status phrase; that is not fixed here. The reviewed multiple_tables, column_span_2 and row_span_2 cases retained their primary structures. None of these directed checks is a population accuracy estimate.

No public binaries or private samples are committed. No merge/deployment. Unmodified repository checks still lack 128 approved assets in the partial checkout, and remote original assets are preserved. Exact-commit CI and actual spreadsheet application acceptance remain separate requirements.

## Final fixed-code validation

- Full cumulative suite: **415 tests run, 414 passed, 1 external Stirling integration skipped**. Independent reviewer passed all 12 rotation tests and approved preserving the existing Stirling route.
- All 34 fixed public files rerun after the final production change: 33 converted, 1 deliberately refused (the independently proven corrupt sideways case). The guard did not create any additional refusal in these sets.
- The vertical_header workbook retains exactly the same values, dimensions and merged ranges, guarding against an indiscriminate non-upright-glyph ban.
- Original 12 ICDAR: 2547/2548 normalized positional text, 2546/2548 text-plus-span, 37/38 merged-cell matches. Next 10: 934/951 normalized positional text, 933/951 text-plus-span, 19/20 merged matches. Counts are unchanged; this is an unsafe-success refusal improvement, not an accuracy-percentage gain.
- A preliminary corpus run was invalidated when the review changed code; the benchmark rejected that mixed-code run and it was rerun against fixed final files. No invalidated result is used below.

Local final evidence SHA-256 (not redistributed):

- `excel-public-icdar/benchmark.json`: `314f2f19233f07ae8345cfb12192004e140221bcd64f1a22551a733e9af3fbe2`
- `excel-public-icdar/cell-evaluation.json`: `d69312cfe42df5c76e13f7aca604398ff07c61f47f37fcaacbb350117557b041`
- `excel-public-next/benchmark.json`: `37ecdd6c17ade2f848d50130c50ca5b44d5659b04d89bef611237833d4674ba8`
- `excel-public-next/cell-evaluation.json`: `78b3186205b88ba851356c2a2c6f579c657dc386b8a52e842c06cc0c46eb9599`
- `excel-public-expanded/benchmark.json`: `306e70e462d12aaaf03be19b7d1af200cb5589680403780d99015a333d08bdaa`
- `excel-public-complex/benchmark.json`: `66d7f257cffc9f964556298ee256192f4e02e2d192095415310f4933246025d1`
- Production `convert.py`: `cdf4233c2fa5480ea207ea8180073e83d36310b8b103d99b91ea40f9727e43fc`
- Production `source_rotation.py`: `58cb348fce3c963db281035cbab2d270d10e73e40fc681a22c76a46c57b27f94`
