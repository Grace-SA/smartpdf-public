# Pinned public annotation protocol

This protocol extends quality work beyond privately held samples. It does not equate generating a file with accurate conversion.

## Fixed selection and separation

`icdar-public-manifest.json` selects EU-001 through EU-006 and US-001 through US-006, before examining results, from Camelot commit `92777b852e00933a5c4b9ba642601784604356cd`. These are 12 ICDAR2013 documents, 39 PDF pages, 37 annotated table/page regions and 2,548 annotated nonempty cells. The selection includes the 15-page EU-004 rather than excluding it for cost. This is not a random population sample or an independently established model holdout; upstream training overlap is unknown.

`prepare-icdar.py` verifies pinned Git blob hashes for all 12 PDFs and 12 structure XML files and records SHA-256 checksums. Inputs and labels stay outside Git. Labels are stored separately and are never passed to the converter. The downloader has a 30 MiB per-file limit, including an early size check on cached files.

## Review defect: silent denominator drift

The prior scorer globbed whatever XML files happened to be present. Independent review reproduced an empty manifest/empty benchmark plus an extra label file producing a seemingly valid 392-cell score. Missing labels, stale extra labels or edited references could therefore silently change evaluation scope.

Default scoring now requires:

- Unique and complete manifest/benchmark identities, with exact source-file and benchmark source hashes.
- An exact declared label set and matching reference SHA-256 hashes.
- Matching XLSX hashes for all successful conversions; refused/error/timeout results remain misses, not excluded samples.
- Version-3 reports binding the actual benchmark and manifest bytes. Comparisons verify these bindings, matching annotation hashes, identical inputs and runtime limits, and matching scoring versions.

Old incomplete historical data requires explicit `--allow-unverified`; that mode is labelled version 2 / `unverified-legacy` and cannot be compared to verified results. The historical 200-file restriction remains for legacy comparison. Verified comparisons support any identical nonempty cohort, including these 12 files. A stale v2 report does not override current v3 results. Missing legacy table-count summaries are reported as unverified, never as passing.

The generic benchmark now reports its actual input count instead of always claiming 200 files.

## Baseline evidence

The fixed engine with atomic workbook handling completed all 12 files under the 180-second per-file benchmark budget. Engine fingerprints were unchanged from start to finish. Runtime ranged from 11.137 to 81.399 seconds in this environment, not a service SLA.

Before native leader recovery:

| Metric | Count / 2,548 annotated nonempty cells |
| --- | --- |
| Exact text at original position | 2,257 |
| Whitespace-normalized text at original position | 2,297 |
| Normalized text and span at original position | 2,295 |
| Row-aligned normalized text and span | 2,508 |

All 12 exports succeeding is **not** an acceptance pass. In particular, US-001 contains dot-leader glyphs assigned to the numeric column; US-002 contains misassigned multi-line headers and a combined section/data label. Whitespace normalization and row alignment can conceal important presentation differences, so exact and position-sensitive results remain visible rather than being replaced by a favorable single percentage.

## Reproduce locally

Use a directory outside the checkout. Provision the repository's pinned model/runtime separately, then run:

```sh
python scripts/pdf-to-excel/prepare-icdar.py "$CORPUS"
PDF_EXCEL_BENCHMARK_TIMEOUT=180 PDF_EXCEL_BENCHMARK_WORKERS=1 \
  python scripts/pdf-to-excel/benchmark.py "$CORPUS"
python scripts/pdf-to-excel/evaluate-cells.py "$CORPUS"
python scripts/pdf-to-excel/compare-runs.py "$BASELINE" "$CANDIDATE" "$COMPARISON"
```

Set `PDF_EXCEL_MODELS` to the provisioned offline models. Do not silently retry with a different engine or discard failed cases. The scorer is an independent local diagnostic, not the official ICDAR competition metric.

## Validation and limits

Five preparation tests and fourteen evaluator/comparison tests exercise cache integrity, bad downloads, resource limits, label isolation, extra/missing/tampered references, duplicate/incomplete benchmark rows, changed sources/outputs, stale score bindings and explicit legacy compatibility. Final cumulative evidence and native leader comparison are recorded with the companion leader-recovery report.

Only downloader/scoring code, public provenance metadata, aggregate results and original synthetic test generators are committed. No input PDFs, XML annotations, derived workbooks or private samples are uploaded. GitHub CI quota and full production/device acceptance remain outstanding; no merge or deployment.
