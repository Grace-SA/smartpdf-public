# Native Gotenberg PoC

Scope and gates are frozen in PLAN.md. This is research infrastructure, not a
production upload service. Only the original six and new ten synthetic DOCX
sources may be sent by run.py. All source/output bytes remain in ignored research
directories. Source hashes must be checked before every batch.

Prerequisites: Linux Docker Engine (locally in WSL or behind an SSH tunnel), normal
project Python tooling with python-docx/Pillow/pypdf/pdfplumber and Poppler.
Generate fixtures once, then verify preparation:

```powershell
python scripts/m13/gotenberg/fixtures.py
python scripts/m13/gotenberg/test_preparation.py
```

Do not rerun fixture generation over a frozen manifest. The preparation tests
cannot establish conversion quality.

Resolve the official gotenberg/gotenberg image to an immutable digest, record
the resolved image and actual engine versions, and keep it identical between the
two variants. Do not call the public demo and call that a self-hosted test.

Run a baseline container bound to loopback, with 2 CPUs/4 GiB memory initially:

```text
docker run --rm --name m13-gotenberg-poc --cpus 2 --memory 4g -p 127.0.0.1:4244:3000 PINNED_IMAGE gotenberg --api-timeout=90s --libreoffice-auto-start=true --libreoffice-max-queue-size=2 --libreoffice-deny-list=.* --api-disable-download-from=true --chromium-disable-routes=true
```

Verify flags against that pinned version. Capture `/version`, `libreoffice
--version`, `fc-match 'Noto Sans SC'`, full installed font names and container
resource constraints before running sources. Keep the raw logs local only.

```powershell
python scripts/m13/gotenberg/run.py --endpoint http://127.0.0.1:4244 --variant default-fonts --repeat 2
python scripts/m13/gotenberg/verify.py --variant default-fonts
```

For the second image, copy this Dockerfile, the existing repository
vendor-fonts/NotoSansSC-variable.ttf and its NotoSansSC-OFL.txt into a local ignored
build context; build with `--build-arg GOTENBERG_IMAGE=PINNED_IMAGE`. No other input
documents enter the image. Repeat the identical sources with `--variant
noto-fonts`. Stop only the container owned by this PoC when changing variants.

Render every candidate PDF using Poppler. Record per-page human visual review
separately: missing glyphs, table/cell bounds, line overlap, image clipping,
headers/footers and page transitions. Add an actual Microsoft Word reference if
available; its source/derivation and authorization must be recorded. Do not use a
LibreOffice export to certify LibreOffice's own Word fidelity.

The independent parser checks text, explicit page count, orientation, page-bound
markers, repeated headers and glyph bounds, and compares repeated-run text/page
geometry. It leaves visualInspectionCompleted and wordReferenceComparisonCompleted
false; passing it must not be presented as complete quality acceptance.

Current setup choice is local WSL/Docker, explicitly selected by the user. Windows
component installation may require a reboot. Resume at environment verification
after a reboot instead of regenerating fixtures or presenting fabricated results.

For the completed study, WSL3.0.3, Ubuntu24.04 and Docker29.9.2 installed without a
reboot. Keep an active WSL process during the experiment: systemd services alone
did not keep this host's distribution alive, and its first container stopped
cleanly between commands. Preserve such failures separately from document runs.

`launch.py` starts only the named PoC container and requires a pinned official
baseline digest. A second occupied container name is refused. It records raw
environment details locally; publish only the reviewed numerical summary.
`table_audit.py` checks PDF line-detected cells against synthetic token positions.
`render.py` creates first-cycle page images and overview sheets for visual review.

The client intentionally expects malformed inputs to return 4xx. In the measured
version, empty DOCX returned 200 and corrupt ZIP returned 500, so batch exit code
is 1 even when all positive PDFs pass. Retain this result; it identifies required
outer input checks and error classification. Do not weaken it to report an
overall pass. The full report distinguishes valid output quality from admission.
