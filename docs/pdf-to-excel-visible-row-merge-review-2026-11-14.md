# Standard-Courier visible row recovery

Scope: optional recovery of a narrowly provable split model row, not general PDF correctness or production approval. No merge or deployment is part of this change.

## Reproduction and independent evidence

Fixed public source: `camelot-dev/camelot` commit `92777b852e00933a5c4b9ba642601784604356cd`, `tests/files/tabula/icdar2013-dataset/competition-dataset-us/us-034.pdf`, page 2, lower table. The original row labeled 0.10 has seven fields: 136 / 144 / 152 / 160 / 200 / 240 / 280. The baseline exported 144, 152 and 200 into a following unlabeled row. Independent review checked the source raster, XML and actual XLSX, not just an aggregate score.

Recovery coalesces the two model rows, preserving every existing nonempty field's complete text, column and metadata; only row indices change. No source string is inserted or split. Empty slots are discarded only in the complementary pair, and custom empty-cell metadata prevents recovery. Original input objects are immutable. Subsequent row indices shift by one; the two heights sum, and widths remain unchanged.

## Deliberately narrow acceptance

- Exactly one candidate complementary row pair, 5–16 columns, 12–100 model rows, at least ten preceding complete rows and a complete following row.
- Final visible source evidence requires all fields in one horizontal text-show, unique field-box ownership, exact whole-field text matches, ordered disjoint columns, and no overlapping page glyphs.
- Target glyphs must use unmodified built-in Courier with no custom Encoding, Widths, FontDescriptor or ToUnicode. Conflicting Courier resources and Type0 resources decline. This does not attest arbitrary font mappings.
- Nontext painting, clipping, images, Forms and unsupported graphics states decline. No hidden text recovery is authorized. Standard PDF apostrophe operations are expanded in an isolated copy to T* then Tj; original/copy RGB pixels and decoded glyph text, bbox, font name, matrix, advance and size must match.
- Existing per-glyph final-render contribution checks corroborate the selected show. Contribution alone is not glyph correctness or semantic certification.
- Font resources, model sizes and comparison work are bounded; optional failures leave the original result untouched. Source stream position is restored on success and failure.

## Verification

Self-contained tests generate source PDFs in memory, with no public/private document assets committed. They cover nonzero leading/character/word spacing and consecutive apostrophes; genuine unlabeled continuation on another baseline; separate-show and same-TJ negative-spacing overprints; misleading ToUnicode; invalid/out-of-text apostrophes; custom Encoding/Widths, font aliases, Type0 and resource limits; covering paint, transparency, clipping, competing ownership and repeated-number wrong geometry; invalid spans, exception fallback and stream restoration. Successful cases assert input immutability, complete field metadata conservation and precise row/height/width changes. Independent final focused review passed all five tests.

Seven fixed public PDFs were rerun end to end with OCR/model settings unchanged, one worker, 180-second outer timeout and unchanged internal model budget: US029, US030, US032, US031a, US033, US034, US035a. All seven converted, 12 tables. Direct actual-XLSX comparison found all existing nonempty field strings and columns unchanged except the intended US034 row reassociation and subsequent row renumbering. All merges unchanged. Independent annotation comparison: 912 annotated fields, 913 output fields, 876 whitespace-normalized aligned matches (previously 873). These are corpus diagnostics, not general accuracy. The remaining differences include annotation errors, leader dots and existing header fragmentation; they are not silently corrected. US034 runtime was34.373s (previous isolated run30.833s); runs were not a controlled speed benchmark.

Full final cumulative suite:570 tests in108.649s,569 passed and1 existing optional Stirling test skipped. Focused final independent review:5 passed in1.112s. Benchmark source fingerprints now also include the new recovery module. The seven-document run preceded that metadata-key addition; its reports do not contain the new key. The separately frozen module SHA256 was004899195a632a64d42fbac5b0cff7bd9bbd7a7445f38fe936dda4b1180737d3; subsequent changes only added the fingerprint metadata key and documentation. The repository asset checker remains blocked by128 previously absent approved assets in this partial workspace. Publication must use the existing complete remote tree and exact changed-text whitelist, preserving every asset; a local partial tree must never replace it. No CI success, Office rendering, real-container deployment acceptance or production readiness is claimed.

## Remaining limits

Does not fix US034 leader dots attached to numeric30, US033 split Total population header, US025 record corruption, arbitrary-font/colored/covered tables, or OCR errors. Unsupported cases retain the previous output and warnings; this change adds no general refusal policy.
