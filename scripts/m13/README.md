# Word to PDF feasibility probes

Research only. No production converter or security preflight. Use synthetic
fixtures only. Engine, generated DOCX, PDFs and logs remain under ignored
`.research/m13/`. The six-source manifest is frozen before conversion.

Prerequisites: normal project Node dependencies and installed Playwright
Chromium/WebKit; Python with python-docx, Pillow, pypdf; existing repository
NotoSansSC-variable.ttf. Python 3.12+ is required for safe tar extraction.

From the repository root, with network access for the first command only:

```powershell
$env:PYTHONUTF8='1'
python scripts/m13/download.py
python scripts/m13/fixtures.py
node scripts/m13/probe.mjs
python scripts/m13/verify.py
```

`fixtures.py` refuses to overwrite an existing manifest. Preserve previous
research directories when starting a new cohort; do not change the fixed six
inputs to turn failures into passes. PDF/PNG outputs are never staged in Git.
Render generated PDFs with Poppler and inspect every page separately from the
structural assertions. `verify.py` does not imply visual or Word fidelity.

For per-case browser isolation, keep this process running:

```powershell
node scripts/m13/probe.mjs --serve
```

In a second terminal:

```powershell
node scripts/m13/diagnose.mjs
```

Optional settings: `PLAYWRIGHT_BROWSERS_PATH` for existing browser installation;
`M13_DEPENDENCY_PACKAGE` for the package.json of a local checkout with installed
dependencies; `M13_CASES` for comma-separated synthetic fixture names (WebKit);
`M13_REPORT` for a report filename; `M13_MEMORY=512` for the intentionally failing
lower-memory import probe. Original reports must be preserved using new names.
The study's four extra isolation inputs are made by `diagnostic-fixtures.py`.

The `memory-worker.js` response instruments the WebAssembly.Memory constructor
without changing the downloaded package. It measures linear memory allocation,
not resident process memory or peak total memory. The smaller-memory test is a
diagnostic; it must never become a production fallback.

Known upstream failures are expected research observations, not passing product
tests. `probe.mjs` writes failures into results.json even when its process exits
normally. Read that file. On the investigated build, image/header import can
hang in desktop WebKit, and upstream destroy aborts. Context teardown is used to
end those research processes, not claimed as a finished user cancellation flow.
