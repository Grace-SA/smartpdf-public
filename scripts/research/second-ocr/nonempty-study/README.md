# Nonempty numeric OCR: correction remains unapproved

This opt-in, fixed-public-input experiment diagnoses two incorrect nonempty
values from the 1901 Census area-table scan. It is **not a detector, generic
correction rule, production integration, or accuracy benchmark**. Fixed field
coordinates select diagnostic crops only; no document-specific replacement is
added to a converter. The production scan still needs manual numeric review.

## Findings

Independent inspection of the original page supports Delaware water area `90`
and Georgia land area `58,980`. The conversion at feature commit
`b012bbd9a828d90a020b86314bba4babc8a13cf4` instead outputs `06` and `58,080`.
Its existing OCR warnings remain necessary; this study does not repair them.

* The observed full-page primary call classified Delaware's box as 180 degrees
  (0.9386) and recognized `06` at 0.9976 confidence. The original-direction crop
  reads `90`, but enabling the angle stage on the tight crop turns it into `06`.
* Georgia's primary result changes between `58,080` and `58,980` when only
  surrounding whitespace changes. The tight crop's wrong result scores 0.9985.
  Tesseract returns two tokens (`58,` and `980`) on that crop and `53,980` with
  four pixels of padding. **Do not join tokens and call this exact consensus.**
* Rotating the Delaware crop makes both direct readers return `06`. That is a
  reading of the transformed pixels, not an established OCR mistake. Agreement
  alone cannot establish the intended orientation of an isolated number.
* A direction label of `180` does not itself prove a rotation was applied:
  the existing classifier rotates only above its threshold. The eight-pixel
  Delaware crop remains `90` despite a lower-confidence `180` label.
* Covered, edge-clipped and duplicated adjacent crops are negative probes. They
  have no assumed source-number truth after transformation. In particular, the
  white crop gets a zero-confidence Tesseract token; any returned string is not
  sufficient evidence of a valid field.

**Decision: do not automatically overwrite either value.** There is no proven
complete-glyph match to two same-column reference cells, unique cell ownership
across arbitrary inputs, or universal orientation evidence. The existing
second-reader research recovery deliberately never overwrites nonempty cells;
this study does not relax that rule. Do not disable angle handling globally,
choose whichever crop matches an expected number, use arithmetic to repair
values, or restore ink hidden by a cover.

## Reproduction without private artifacts

Use the parent research setup for the pinned Tesseract executable, English
model, resource wrapper and generated `engine-lock.json`. Keep its deployment
limitations. This directory adds no downloads, binaries or production hooks.
Use Python 3.12 and the exact six package versions and three primary-model
hashes in `inputs.json`. The new renderer dependency is `docling-parse==7.25.0`;
other versions are checked before recognition. These are the observed existing
research environment, not a newly validated container image.

Download the [official Census PDF](https://www2.census.gov/library/publications/decennial/1900/bulletins/geography/57-area-square-miles.pdf)
outside Git, preserving its original bytes. Its SHA256 is locked in
`inputs.json`. The script refuses any different input before parsing. It
renders PDF page 2 using the pinned Docling parser at scale 3, then verifies the
complete RGB raster hash and dimensions. This exactly reproduced the pixels
captured at the real OCR input, unlike a direct PDFium render tested separately.
It then extracts two declared integer boxes and produces the twelve fixed
variants. No local `ocr.json`, screenshot, workbook or crop file is required.

```sh
OMP_NUM_THREADS=2 python -m unittest discover -s nonempty-study -p 'test_*.py'
OMP_NUM_THREADS=2 python nonempty-study/reproduce.py --enable-research \
  --source /outside/repository/57-area-square-miles.pdf \
  --output /outside/repository/nonempty-report.json
```

Run from the parent second-OCR research directory. Without the explicit opt-in
flag, the script refuses. It writes only the diagnostic report, never a repaired
workbook. Do not commit source PDFs, rendered pages, crops or full OCR traces.
The original PDF is a historical US federal publication. No source image or
full document text is redistributed; the package contains only code, hashes,
selected measurements and findings.

## Budget and validation

One research job handles all twelve supplementary calls, not a reset budget per
field. Existing caps remain: 12 calls, 8 cumulative subprocess seconds, 2-second
per-call wall/CPU bounds, 256 MiB child address-space limit, 64 KiB output and
16,384 crop pixels. Inputs/results use the existing sealed anonymous-file
protocol. Tesseract is the existing fixed 5.3.0 English model with PSM 10; this
is a single-character-oriented diagnostic configuration, **not** proof of a
production multi-digit reader. No PSM or dependency was silently upgraded.

The captured run used 1.674 cumulative subprocess seconds; direct primary
recognition totaled 0.350 seconds and angle-plus-recognition 0.352 seconds.
A standalone source-to-report reproduction gave identical twelve crop hashes,
reader tokens, confidences and angle outputs; supplementary time was 1.522
seconds. These exclude setup/rendering from the quoted component totals and
are not full-document incremental costs or throughput guarantees.

Child peak RSS was 152,268 KiB in the captured-image harness and 259,684 KiB in
the standalone renderer harness. These observations can include pre-exec child
state; they are **not incremental Tesseract RAM or validation of total process
memory containment**. The inherited address-space limit is set in the child
launcher, not a cgroup or service-wide RSS limit. No actual container, global
admission or deployable-image acceptance has been performed.

Four added tests cover source rejection before parsing, runtime/model mismatch,
bounded variants with no source mutation, and required opt-in. The parent
research suite also passed all 30 tests (4.843 seconds); these are separate
from the four focused tests. An independent reviewer passed the four focused
tests and reviewed the five-file package, but did not repeat the full dual-reader
run. Neither these tests nor this twelve-case
experiment establish broad OCR correctness or production readiness.
