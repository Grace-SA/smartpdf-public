# Refuse proven outer-label reversal in nested tables, 2026-11-14

Base: `c39e316b3100802b467af5a6c78545231f312bfe`.

## Source evidence

The pinned public tableception PDF has a closed outer grid containing one closed inner table. Native physical extraction independently produces the outer 5-by-9 grid and inner 7-by-3 grid. The model flattened them into 13-by-11, retaining the inner numeric values but splitting outer labels. In one source cell, the two visually ordered lines are "Under" then "surveillance"; exported model rows reversed them. Other outer disease/serial spans are also imperfect.

This change does not guess the correct spans or reconstruct those labels. It prevents a demonstrated corrupt successful export from being presented as usable.

## Refusal proof and exclusions

The optional final-adapter check requires exactly one strict nested pair of complete closed physical grids, complete nonoverlapping grid coverage, a child lying inside exactly one parent cell, and bounded workload. A candidate is a short ASCII, nonnumeric, one-column parent label outside the inner table. Two to four model fragments must remain in the same logical column, with separate row indices and source boxes entirely in that parent cell.

Source glyphs must be horizontal, upright, same font and size, inside the cell, grouped into separate nonoverlapping baselines, and uniquely owned by those model fragments. Source extraction must exactly match the physical cell's words. Only when model row order has exactly the same word multiset, including repetitions, but a different sequence does the exporter refuse. Images, annotations, overlapping/ambiguous boxes, incomplete grids, multiple nested candidates, numeric labels, non-ASCII labels and differing word content do not meet this proof.

It neither moves numbers nor normalizes Unicode, inserts rows, replaces words or repairs PDF metadata. An unflagged nested table is not certified correct; many layouts lie outside this narrow check. Native glyph evidence is not a general raster-visibility proof under arbitrary clipping or transparent/overpainted text.

## Tests and independent review

Synthetic cases cover reversal, valid multiline labels, repeated words, changed word counts, numbers, Unicode, touching/ambiguous/nonclosed grids, internal-table labels, cross-column fragments, image/annotation overlap and mixed glyph geometry. A real synthetic PDF test uses actual physical-grid and glyph extraction, injects a faulty neural result, and exercises the final layout adapter refusal. It is not a real-model accuracy test; the pinned public sample separately exercises the actual model path.

Independent review approved the narrow refusal and requested the real-PDF integration case; it was added. The public sample now raises a clear conversion error and produces no new XLSX. A separate run confirmed the original PDF and an existing destination file remain byte-for-byte unchanged.

Known multi-level-header, missing-span and character-decoding limitations are not fixed. The benchmark fingerprint includes the new guard module. Public input binaries, annotations, output workbooks and private data are not committed. No merge/deployment. Partial-checkout asset and exact-commit CI limitations still apply.

## Final fixed-code results

- Cumulative Python suite: **421 tests run, 420 passed, 1 external Stirling integration skipped**. All six new guard tests passed independent review.
- All 34 fixed public files rerun: 32 converted and 2 deliberately refused. The refusals are the previously proven sideways case and this newly proven nested-label reversal; no other new refusal occurred.
- Original 12 annotated PDFs: 2547/2548 normalized positional text, 2546/2548 text-plus-span and 37/38 merged-cell matches. Next 10: 934/951 normalized positional text, 933/951 text-plus-span and 19/20 merged matches. Scores are unchanged; refusing a corrupt export is not a recognition-accuracy percentage improvement.
- The unmodified repository checker remains blocked by 128 existing approved assets absent from this partial checkout, not by new input binaries or personal material. Remote original assets are preserved. Exact-commit CI, actual spreadsheet application rendering and full product release acceptance remain unverified.

Final local evidence SHA-256 (not redistributed):

- `excel-public-icdar/benchmark.json`: `884c4c40368d2dd8d254ddda3a0c5ed34af9ca42965d1b6104f871739599bc1f`
- `excel-public-icdar/cell-evaluation.json`: `de81456e5426b4925d7fdc99880de23e8b55a3bb664046738732a43ffd94b82a`
- `excel-public-next/benchmark.json`: `b2662060ed2eba864c8f18d473fad111e6afad29090fba9adddc8099c9508d95`
- `excel-public-next/cell-evaluation.json`: `d05161f20b2a5fb7ac12721ae1ae5bb8650a6e400c40feb5abef6fe4e2929024`
- `excel-public-expanded/benchmark.json`: `390b42b87df223ea7724de0bf28bc762659ef31a606c4d3b704b5553e1583a67`
- `excel-public-complex/benchmark.json`: `c9ee3da08a07ce5b2058f01918fba8b64369a279ddbc4e4fb8890a658ddb1259`
