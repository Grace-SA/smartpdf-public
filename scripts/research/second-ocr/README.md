# Default-off second OCR research (not production)

This directory is an isolated experiment based on `eef241f69fb67fbc75d5861925a5ff84fc222b0b`. Nothing imports it from the production service, modifies its Dockerfile or starts it in CI. Do not merge it into a deployment path. No PDFs, receipts, crops, model weights, Debian archives, credentials or dependency binaries are included.

## Reproduce the focused tests

Use Linux amd64, Python 3.12, `patch`, `dpkg-deb` and a disposable research environment. The observed host was Debian 13; the extracted OCR packages are Debian Bookworm. This mixture is **not a validated Bookworm container**.

From this directory, with the repository checked out:

```sh
python -m venv .venv
.venv/bin/pip install -r requirements-tests.txt
.venv/bin/python fetch_dependencies.py --download
.venv/bin/python prepare.py --repository ../../.. --extracted-debian-root root
.venv/bin/python -m unittest discover -s . -p 'test_*.py'
```

Downloads are from the official Debian archive, checked against fixed archive sizes and SHA256 values before local extraction, never installed system-wide. The original research also verified the signed Debian InRelease→Packages→archive chain. This publication pins the resulting archive identities; it does not include or revalidate a fresh signed index. If old archive URLs disappear, stop and independently verify a replacement rather than silently upgrade. `prepare.py` verifies all 51 baseline Python files before copying them into this directory's ignored `engine/`, applies the local patch, and checks the pinned OCR binary/library/model. Running it changes no production files. The generated local lock contains machine-specific paths and must not be committed.

30 focused tests passed after final independent review. They cover digit evidence, adversarial geometry/ink, malformed TSV, engine disagreement, unavailable dependencies, timeout/output/memory bounds, task budgets/concurrency, cancellation, descriptor sealing, partial creation failure, and SIGKILL probes. They are not the full production test suite or a broad accuracy benchmark. The test fake executables are self-authored probes, not alternative OCR engines.

## Explicit end-to-end research use

Install the existing service's pinned Python requirements into a separate research environment and provision its verified primary OCR models following `server/pdf-to-excel/README.md`. Keep `PDF_EXCEL_MODELS` pointed to those models. The opt-in command is:

```sh
python run_research.py --enable-research input.pdf output.xlsx
```

Without `--enable-research` the public harness refuses to run. Calling the recovery module without a research-job context also exits before glyph analysis or supplementary OCR. The generated isolated converter is an internal test artifact, not a service entry point. No network download is performed by the second reader at recognition time.

The three public source identities are in `public-sources.json`. The recorded experiment rasterized their pages at 150dpi into image-only PDF simulations, then compared frozen baseline and research workbooks. `final-comparison.json` records the resulting scan identities, timings and exact cell differences. Source PDFs and generated scans are intentionally not redistributed. Rainfall changed only A18 from empty to `3`, improving the previously checked 409/411 nonempty fields to 410/411; `NORTH WWEST` remains wrong. The other two workbooks were unchanged, including dimensions and merges. These are controlled scan simulations, not an independently acquired true-scan cohort. A separate supervised rainfall run matched the direct candidate cell-for-cell. Timings are whole conversions, not incremental second-engine costs.

## Scope and safety boundaries

Only empty, single-span, physically enclosed cells qualify. Exact complete grayscale glyphs and whitespace must match at least two same-column references, with independent fixed Tesseract confirmation. There is no sequence inference, numeric whitelist or sample-specific value. Existing values are never replaced. Rendering comes from the final PDF so visual covers are not bypassed.

Linux anonymous memfds carry input PNG, validated configuration and output TSV. Input/config seals prevent modification. The launcher closes the config descriptor before exec and disables its own core dumps. Anonymous-FD failure returns no recovery, with no named-file fallback. The reader is limited to 256MiB address space, 2-second per-call wall/CPU bounds, 64KiB output, 12 calls and 8 cumulative subprocess seconds per job. This is not a service-wide concurrency budget or OS sandbox.

The SIGKILL probe found no named second-reader payload residue; an empty job directory may remain. Linux frees anonymous storage after all handles close, but this is **not secure memory erasure**, swap protection, debugger isolation, or cleanup of source PDFs/final workbooks. Another negative test deliberately shows arbitrary files from other components can remain when the supervisor is hard-killed. Its caller must still own document retention and crash recovery.

Independent review fixed NaN confidence handling, discarded-edge ink including exclusive boundaries, primary retry exceptions, cleanup-error signal restoration, and truncated/extra-column TSV fallback. No production approval follows from these focused tests.

## Deployment gates still open

- A complete pinned Bookworm image build and smoke/visual/content validation; no usable container runtime was available for this research.
- Full image SBOM, license/source obligations and vulnerability review. `LICENSE-INVENTORY.md` covers only observed selected packages and clearly distinguishes unverified host-loaded dependencies.
- Immutable executable/model/loader paths; checksum checks do not remove writable-filesystem TOCTOU.
- OS/container network/filesystem/process isolation and global service capacity limits.
- Complete source/output lifecycle, cancellation/host-loss retention policy, broader real scans and adversarial coverage.

Selected packages were about 13.7MB downloaded / 48MiB extracted, **not** the incremental size of a complete deployable image. Small-crop observations were about 0.12–0.17 seconds and 56–63MiB child peak on this host. Do not treat these as throughput guarantees or universal OCR accuracy.

### Recreate the public comparison

Download only the three official pinned URLs from `public-sources.json` into a local directory (not committed). In the end-to-end environment also install `reportlab==4.4.9` and `pypdfium2==5.14.0`. With the primary OCR model configuration described above:

```sh
OMP_NUM_THREADS=2 python reproduce_public.py --enable-research \
  --source-directory /path/to/public-native-pdfs --repository ../../.. \
  --output-directory /path/to/new-empty-research-results
```

This first enforces the pinned renderer versions (including PDFium 156.0.8076.0) and all 51 baseline hashes, then verifies the native source hashes, renders at 150dpi with PDFium and text/path/image smoothing disabled (the historical simulation settings), then wraps the images with ReportLab at the exact page width and height, without aspect-ratio fitting, creates image-only PDFs, runs baseline and prepared research engines, and checks sheet names, dimensions, merges and exact cell differences. It reports the newly generated simulation hashes separately. PDF serialization IDs can vary, so regenerated PDF hashes need not equal the historical simulated-PDF hashes in `final-comparison.json`; source identities, renderer version and workbook comparisons are the reproduction checks. Output files remain local and must not be committed.

Publication preflight caught and rejected a default-smoothing reconstruction: it did not reproduce the historical scan. With all three PDFium smoothing options disabled, all three recreated page rasters matched the historical embedded RGB pixels exactly. This demonstrates why renderer settings are part of the fixture, not interchangeable implementation details.

A second publication preflight rejected an aspect-fitted wrapper: even identical raster pixels are insufficient if embedding shifts/scales thin grids. The reproducer therefore uses the historical ReportLab full-page transform, not an aspect-fitted image wrapper.
