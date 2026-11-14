# Recover indexed text registers without weakening content protection

Base: `72d088133e8863f5ba395e4854ddd2c4b0a019c2`, branch `codex/pdfword-general`.

## Reproduced coverage gap

Of the fixed 18 public PDFs, 16 were refused. Inspection distinguished paint/rotation/clip uncertainty, encrypted or active files, incomplete grids, and ambiguous layout. These restrictions were not removed. One two-page public Camelot sample, `hybrid_multipage.pdf`, passes native paint safety and has ordinary text-valued records, but the borderless-table recognizer required numeric data columns. Its 3-column text register was rejected as an ambiguous sparse grid.

Both source pages independently show a thin horizontal header separator spanning all columns. Header left edges differ from body edges by 2.8pt; source body columns align exactly. Recover this narrow class, not arbitrary numbered lists.

## Conservative evidence

- At least three columns, three body rows, short single-line cells, same column count.
- First row is non-numbered; body keys are unchanged positive ASCII integers without leading zeros, consecutive and never restarted.
- Each body column is left- or right-aligned within 2pt. Header cells participate in globally disjoint column bands, with at least 12pt separation. No header-to-body 2pt/3pt edge claim is made.
- A real thin horizontal source line spans all candidate columns between the header and first body row. The 1pt bounding tolerance accommodates font boxes, not an exemption from visual proof.
- Final 144dpi raster evidence: at least 95% of the candidate width has line-band pixels at least 40 gray levels darker than both sampled neighboring bands. This rejects absent, white, fully transparent and subsequently covered lines. Rendering is bounded to 16MP; grayscale is cached per page. At most 32 probes and one million sampled pixels per page are allowed; exceeding either budget fails closed.
- Nearby malformed/missing/wrapped rows cannot be left behind while accepting a valid prefix. Two-column lists, absent/short/misplaced rules, non-consecutive keys and misaligned columns remain unsupported by this route.

No changes to paint occlusion, source preflight, OCR thresholds, source strings, header-role inference or cross-page linking. A raster is inspected only as structural evidence; no content is uploaded or OCR invoked by this route.

## Validation

Six new synthetic test methods cover genuine two-page editable conversion with exact cells and edit/save/reopen; missing, short, misplaced, white, transparent and covered rules; failed rendering; restarted/skipped/punctuated/zero-padded keys; missing cells, continuation text, misalignment, overlapping header and two-column lists. A 100-candidate counterexample verifies one render, one grayscale conversion and at most 32 pixel probes.

Full core suite: 173 tests, 170 passed, 3 optional OpenCV scan tests skipped. Those same 3 tests pass separately in the provisioned OCR runtime. Existing paint, list and table defenses remain in the suite.

Public replay: 3/18 now convert instead of 2/18. Only `hybrid_multipage` changes status. Its two tables preserve all 30 independently checked cell strings in their exact rows and columns, including both header rows; no automatic inter-page concatenation. The two already supported public outputs have byte-identical document.xml before/after. All 18 source hashes are unchanged. Remaining 15 refusals include 13 requiring configured OCR, one encrypted file and one active-content file.

Independent review identified invisible source rules as false evidence; pixel verification and white/transparent/covered regressions address that finding. Review also requested a cumulative work limit, now enforced with cached grayscale and explicit probe/pixel budgets. No public PDF/DOCX binaries are committed.

## Limits

This is a narrow coverage increase, not general table understanding or production readiness. Wrapped cells, missing cells, most rotation/complex-grid cases and OCR provisioning remain outstanding. PDF source rendering is verified; final Office pagination/appearance cannot currently be verified because local LibreOffice conversion fails. Full unmodified repository checking is blocked by 129 baseline allowlisted assets absent from this partial checkout. Remote base-tree commit preserves all assets. No merge or deployment.
