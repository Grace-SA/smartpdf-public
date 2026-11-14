# Recover uniformly turned content with zero page rotation, 2026-11-14

Base: `cd14adf92618cd973e3209b020e37d61ea013e8c`.

## Actual coverage improvement

The pinned public Camelot `anticlockwise_table_1.pdf` has `/Rotate=0`, yet all 781 visible non-whitespace native glyphs are turned 90 degrees. The previous preprocessing considered only nonzero page metadata and the subsequent safety guard refused this file. The existing strict normalization now also considers zero-metadata pages whose visible native glyphs all share an exact nonzero quarter-turn. The real model exports a 13-by-10 table: two header rows and eleven records. Independent source/output inspection matched all 99 numeric or starred values and the relevant header merges. This is one demonstrated recovered conversion, not an estimate of general accuracy.

The three new public inputs are pinned in `rotation-public-manifest.json`; PDFs and output files remain local. `clockwise_table_1` still converts through its existing metadata-rotation path. `clockwise_table_2` remains refused without the external Stirling service. The existing complex mixed-direction anticlockwise sample and nested-table reversal remain refused.

## Boundaries and rejected alternatives

The added path excludes images and annotations, rejects mixed directions, uses the existing dimension limits and caps candidate glyph count at 50,000. The glyph-count check happens after parsing and is not a parser memory bound. Full glyph multisets must remain unchanged and all visible result baselines must be horizontal. No OCR, character substitution, row movement or numeric correction is introduced. Source bytes are not changed.

A separate rigid-rotation experiment on the complex anticlockwise sample produced identical rotated pixels, but the real model still mixed the title into the first record and damaged header alignment. Pixel equivalence alone therefore did not justify relaxing the mixed-direction refusal. No such relaxation is included. Nested-table reconstruction also remains unresolved rather than guessed.

Ordinary upright pages now require an extra orientation probe compared with the old baseline. They do not create a trial PDF or undergo a second normalization parse, and each probe page cache is released. Informal single-run measurements reduced the initial prototype's added preprocessing from 0.427 to 0.188 seconds for health and 2.154 to 0.847 seconds for EU004; these are not throughput guarantees or improvements over the old no-probe baseline.

## Verification

Synthetic tests cover three content-turn directions, with and without crop boxes, exact PDFium rotated-pixel equality, exact native exported cells and unchanged original bytes. Image and annotation cases remain unchanged. An upright-page test prohibits construction of a trial writer. An independent reviewer reran all 14 focused rotation tests and found no blocking issue, including after the probe optimization.

Public outputs are independently checked where described; conversion success alone does not certify table semantics. Known US008 grouped-section rows, decoded ligatures, multi-level headers and complex nested spans remain limitations. No production readiness, deployment or merge is claimed.

## Final frozen-code checks

- Cumulative Python suite: **423 tests run, 422 passed, one external Stirling integration skipped**.
- The unmodified repository checker was run. This partial checkout is still blocked by 128 previously approved assets missing from its index; no new binary or private input is added. The remote base tree will preserve all existing assets.
- Exact-commit GitHub CI must be checked separately; local tests are not a CI pass.

Frozen benchmark report SHA-256 values (local artifacts, not redistributed):
- rotation: `3a742e62159ecfc6c570cfe68ffd49e21831b4e2dccad126447109247090a3a3`
- complex: `5ab28da1a3ef21a714f9e9f1de738efc83312fd9902353d9bb32a9ac45902f4f`
- expanded: `38589f10d74ebe8484b28ce32d2bf4af46133d3bcdc6cd0c9ba5b865b850563a`
- icdar: `41e67c2c7966c1d220bd25d59b7408a401a57969eb3684d978bc598e736c9d9a`
- next: `9fecbff14a4ca13fff3b346673f244748a434a20c74287f32bab91b282c2d27f`

All 37 public PDFs were rerun with matching final engine fingerprints: **34 exported and 3 conservatively refused**. The refusals are complex mixed-direction anticlockwise_table_2, nested-label-reversal tableception, and clockwise_table_2 without Stirling. Export success is not a content-accuracy verdict. The original 22-file comparison remains unchanged: initial 12 files 2547/2548 whitespace-normalized cell positions and 2546/2548 text-plus-span; next 10 files 934/951 positions and 949/951 row-aligned normalized values.

Recovered anticlockwise_table_1 output SHA-256: `4a529b3a0f929926f0b78b64ca958d0340e665b90dd24e02be354cb23cb96bed`.
