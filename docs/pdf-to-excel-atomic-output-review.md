# Atomic workbook publication and XML safety

Follow-up to `351c9d8aad9865bcad0770487f6d2025c2ac8008`.

Independent review generated an original synthetic native-table PDF whose font ToUnicode mapping maps a visible character to U+FFFE. The prior converter raised an XML serialization exception and left a 2,293-byte incomplete XLSX. This is a direct Python/CLI writer contract defect. The service already removes failed job directories and disallows failed downloads; no online information disclosure is claimed.

## Changes

- Reject XML-forbidden U+FFFE/U+FFFF and isolated surrogate cell characters with a clear conversion error. Do not silently remove or replace source characters.
- Serialize into a private temporary directory beside the destination. Attach form rules, perform independent checks and enforce the download-size limit before an atomic replacement of the requested output.
- On serialization, validation, size or replacement failure, remove temporary artifacts and preserve any prior destination. No partial ZIP is published.
- Verify external relationships as well as worksheet formulas. This closes a defense-in-depth gap in an existing check's stated contract; it is not evidence of a previously demonstrated PDF-driven external-link injection.

## Validation

Six new tests cover valid publication, failed serialization both with and without a prior output, size rejection, illegal Unicode including a real PDF font mapping, and external-relationship fault injection. Independent review additionally injected formula-check and `os.replace` failures and verified prior-file preservation and temporary-directory cleanup.

Pinned-model cumulative regression at this engine state: **249 tests, 248 passed, 1 skipped**, 81.142 seconds. The skip remains external Stirling. The six new tests and four form-rule tests also pass independently. Python syntax and critical Ruff checks pass. The sparse repository guard reports only the same 129 missing local approved assets; remote binary assets remain unchanged.

No private samples or public PDFs are committed. No merge, deployment or CI-success claim. This hardens output handling, not general conversion accuracy; public annotated coverage evaluation is being expanded separately.
