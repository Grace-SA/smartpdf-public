# Multi-page empty-row/merge validation and runtime recovery, 2026-11-14

Base: `1936e1be85c8e90a9cd617a2da513e24060ac3df`.

## Outcome

This round adds validation, not another claimed production-code fix. No new data-integrity defect was reproduced in the tested multi-page empty-row/merge cases. The previous physical-empty-row correction remains intact.

Four end-to-end tests generate an original three-page document containing explicit blank rows, mixed merged/unmerged page grids, leading-zero identifiers, decimal amounts, tail labels and distinct page context. They cover separate worksheets, one shared worksheet, nonconsecutive page selection and an actual raster-only three-page scan recognized by RapidOCR. No recognition result is mocked. Checks include every table cell, exact merge sets, original page identity, exclusion of other/unselected page context, and independently inspected XLSX XML merge references. Independent review passed; its requested stronger exact-value/context checks were added.

These are clean synthetic documents, not a representative real-world accuracy measurement. Success is not described as 100% OCR accuracy or general production readiness.

## Recovered environment

- Created an isolated runtime using official PyPI packages and PyTorch's official CPU wheel index. All **87 requirements in the existing runtime lock** satisfy their pinned version specifications; repository lock files were not changed.
- Restored the repository-reviewed CJK fixture font. Its 17,772,300-byte size and SHA-256 `a3041811a78c361b1de50f953c805e0244951c21c5bd412f7232ef0d899af0da` match the existing inventory.
- Restored all eight pinned layout/TableFormer model files from the official model repositories at the manifest revisions. Every file's size and SHA-256 matches `server/pdf-to-excel/models.json`. The setup client's home-cache restrictions were avoided by downloading the exact revision files into the isolated workspace and checking the unchanged manifest; no model or hash was substituted.
- Conversion/test execution used offline model settings. No user document or private receipt was sent externally. Package/model provisioning was setup only.

The earlier partial-runtime run's 14 errors were not suppressed. Restoring the packages/font removed those blockers; provisioned verified models then resolved the remaining scanned-borderless fixture failure. The final locked-runtime suite is recorded below.

## Final validation

- **403 tests run: 402 passed, one skipped** because no real Stirling service is configured. No assertion failures or errors. The four new multi-page tests all execute and pass, including real OCR.
- Compileall passed. The current Word pipeline was also rechecked in the restored environment: 161 Python tests passed, zero skipped. This does not provision or validate Word's separate Paddle/MLX recognition engines.
- The unmodified repository guard still reports 128 reviewed binary assets missing from the partial local index after restoring the verified font. No guard was weakened. Only the synthetic test generator/assertions and this aggregate report are added to the existing GitHub tree; no generated PDF/XLSX/image, model or dependency environment is committed.

## Remaining release work

Actual Excel rendering, representative private/public acceptance corpora, complete frontend/build/browser checks, the full asset checkout, real Stirling integration and successful exact-commit CI remain outstanding. No production code is changed in this round; no merge or deployment.
