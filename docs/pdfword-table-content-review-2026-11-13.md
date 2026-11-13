# PDF to Word: OCR table content preservation review

Base: `dad8a4f7e00559982a8df19a1e392fcf5436dda8`, branch `codex/pdfword-general`.

## Reproduced failures and corrections

- Adjacent HTML paragraphs in an OCR table cell were concatenated. For example, separate amounts `12.34` and `-56.78` became `12.34-56.78`. Block boundaries now survive as editable Word line breaks. Inline formatting remains contiguous, so an amount split across bold/span/italic elements remains `12.34`.
- Text or paragraphs outside actual table cells were accepted but omitted from the output. Structural validation now refuses such unassigned content instead of claiming a complete conversion. Whitespace and ordinary table row groups remain supported.
- Independent review caught an additional superscript/subscript shortcut that concatenated line-separated digits, plus formatting whitespace that could introduce extra blank lines. Both were corrected and covered by regressions.
- Existing merged-cell ownership, Unicode text, numeric super/subscripts, explicit repeated line breaks and editing/reopening are preserved.

## Verification

- 12 new regression tests; running them against the unchanged base model produced 13 failing assertions (including parameterized structural-text cases), confirming the repros.
- Final complete available PDF-to-Word Python discovery: **59 passed, zero skips**, using pinned pypdfium2 5.14.0, pypdf 6.21.4, python-docx 1.2.0, pdfplumber 0.11.9, Pillow 13.0.0 and lxml 6.1.1. OpenCV preprocessing tests additionally used opencv-python-headless 5.0.0.93 and NumPy 2.5.4. These optional local test dependencies do not change the production requirements.
- Python compilation passed. A separate reviewer reran all 12 added regressions and found no remaining blockers in this scope.
- Three original synthetic DOCX examples (multiline amounts/units, merged headers, Chinese text) were exported and independently rendered by LibreOffice. All three were one page; extracted text retained separate amounts, line boundaries and characters. All three rendered pages were visually inspected for clipping/overlap. A regression also verifies the saved DOCX XML line break directly after edit/reopen.

## Release status and limitations

This is a focused correctness improvement, not a new general-coverage percentage. The private 139-input corpus, original OCR models, Microsoft Word and target production environment were not available here. No private document, image, inventory or rendered output was added to Git.

The repository guard was executed unchanged against the partial source index. It reports 129 previously approved binary assets missing from that partial checkout; therefore the **complete repository guard is not passed**. The source patch is published using the original remote tree so all unrelated files and binary assets remain unchanged. Full-site browser/JavaScript regression and actual model inference were not rerun. The user has confirmed GitHub Actions quota is exhausted; local tests do not replace successful exact-commit CI.

General production readiness remains false. Complex-table fidelity, the fixed whole-corpus rerun, independently checked content coverage, real Word/platform checks and production performance remain required. No merge or deployment is performed.
