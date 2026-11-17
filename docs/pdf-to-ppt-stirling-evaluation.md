# PDF to PPT: Stirling evaluation (2026-11-11)

Status: viable self-hosted experimental engine, **not production accepted**. This report does not enable a website feature or change the pinned Office-to-PDF deployment.

## Decision and dependencies

Reuse the existing pinned Stirling **3.2.2 core**, not an unpinned full distribution. The tested official server JAR matches `config/word-core.stirling-3.2.2.json`: SHA-256 `370a4218624fa4b3cf5460c886f03de01bfcfd2d4893009202a81e53b5f3344d`. Embedded native office converter version: `0.2.2`. Source commit: `684608d143779bf3a8ffc67639f077a1202c62ff`.

The Java conversion path needs Java 25, server CPU/memory, temporary disk and fonts. It requires no Adobe account, commercial cloud API key or external conversion request. OCR remains a separate dependency for scans. LibreOffice is useful as an independent output renderer and is required for the alternate conversion path. A production deployment still needs the existing queue, request limits, isolation, expiry, monitoring and font/license controls.

This experiment used the official API-only JAR on macOS ARM64 with Temurin 25.0.5+8, a 1 GiB Java heap and two active processors. It listened only on loopback; an OS sandbox denied outbound Internet while conversion ran. This is **not** evidence for the Linux production image or its resource envelope. Production pins were unchanged.

## Exact API and configuration

Write overrides to `configs/custom_settings.yml`; `settings.yml` is generated and was overwritten during the initial startup experiment.

```yaml
system:
  stirlingOfficeConversion: true
  enableAnalytics: false
  enablePosthog: false
  enableScarf: false
  showUpdate: false
```

Request `POST /api/v1/convert/pdf/presentation?useStirlingOfficeConvert=true` with multipart `fileInput` and `outputFormat=pptx`. The explicit flag selects the native Java engine; its system default is false and upstream labels it beta. This endpoint does not itself OCR scans.

The alternate `useStirlingOfficeConvert=false` route invokes LibreOffice with `impress_pdf_import`. Two synthetic requests returned HTTP 500 in the bundled macOS LibreOfficeDev 26.8 alpha environment: no PPTX export filter for the imported document. That environment lacks the `impress_pdf_import` registry entry. The attempt was stopped; no 200-file LibreOffice benchmark or conclusion about production LibreOffice quality is claimed. This differs from the repository production baseline and must be retested in the pinned Linux image.

## Real conversion evidence

Inputs and outputs, source URLs/hashes, individual results and screenshots remain local. Public availability does not authorize redistributing each upstream PDF. No corpus inventory, binaries or page images accompany this report.

| Check | Observed result |
| --- | --- |
| Public corpus | 200 unique downloaded PDFs; fixed source revisions and SHA-256 identities |
| Preflight | 184 accepted / 16 refused |
| Actual native conversion | 184/184 accepted PDFs produced parseable PPTX with matching slide counts; 554 pages |
| Text diagnostic | 48 documents / 95 pages triggered character recall or precision below 99.5% |
| Numeric diagnostic | 43 documents / 116 pages triggered numeric token differences |
| Combined text/number diagnostic | 63 documents triggered one or both; the other 121 are not automatically quality-approved |
| OCR candidates | 44 documents / 49 pages need OCR ground truth |
| Synthetic fixtures | 14 valid PDFs / 28 pages converted; 3 expected refusals (encrypted, corrupt, over page budget) |
| Synthetic text/numbers | No extracted character or numeric diagnostic mismatches on the 14 valid PDFs; scans have no extracted reference text |
| Semantic assertions | 8 passed: table dimensions/cell values, edit-save-reopen, merge span, editable Chinese, scan limitation, refusal set, extracted text/numbers |
| Prototype automated suite | 65 passed, including existing tests and 18 Stirling adapter cases |
| Real integration smoke | Upload, isolated worker, actual Stirling conversion, PPTX checks, needs-review state, download access control and deletion passed |
| Independent render, corrected fonts | 184 public PDFs / 554 pages and 14 synthetic PDFs / 28 pages compared; 145 public and 12 synthetic documents triggered conservative pixel review flags |

The corpus contains upstream parser/regression fixtures and difficult edge cases. It is useful for robustness testing but **not a representative customer-document accuracy sample**. Character histograms ignore order; separate reading-order warnings exist. OCR has no human transcript baseline. Numeric diagnostics and text extraction can themselves need manual adjudication. These numbers are screening evidence, not a claim of 100% text accuracy or a business success rate.

Warm local conversion wall time across accepted public PDFs: median 0.0565 seconds, maximum 7.373 seconds, including adapter/preflight/structural checks. Sequential, small-file-heavy, local-only results are not capacity or production latency benchmarks.

Refusals: 10 invalid PDFs, 3 encrypted PDFs, 1 unsupported XFA form, 1 invalid page-dimension case, 1 unsupported encryption implementation.

## Layout, editability and environment findings

All accepted public and synthetic outputs were opened and rendered through a different implementation, LibreOffice. Initial CJK rendering omitted Chinese despite correct editable PPTX XML. An isolated Fontconfig configuration with the repository's licensed Noto Sans SC font and a SimSun substitution resolved that fixture's missing glyphs without changing the PPTX. Font substitution changed appearance; exact typography is not established. Provisioning a font on the conversion server also does not ensure a recipient has it installed.

Manual visual checks covered CJK, two-column text, ordinary and merged tables, vector graphics and orientation. Ordinary/merged synthetic tables are native PPTX tables: 6 rows, 3 columns, with the merged header retaining a three-column span. A cell was changed, saved and reopened successfully. Layout differences remain (for example the synthetic square/circle graphic shifts vertically). Scan-only pages remain pictures. A scan must not be advertised as editable text.

Pixel-difference reports are conservative review signals; rasterization, fonts and antialiasing affect them. They are not OCR/semantic quality scores. Full manual review of all 554 pages, Microsoft PowerPoint, WPS, real-device browser acceptance, concurrency/load testing, production Linux testing and scanning/OCR acceptance have **not** been completed. Local browser automation was not performed.

Three manually reviewed public problem pages confirmed substantial defects: a table of contents reflowed into paragraphs, a complex diagram stretched over body text, and a wide numeric table overflowed the slide with compressed/misaligned columns. These are sufficient to reject an unrestricted high-fidelity production launch, independent of the diagnostic thresholds. The auxiliary rendered-PDF text report also emitted missing-fontTools warnings for some Type1 fonts; do not use those auxiliary values as accuracy evidence. Main text diagnostics above compare PDFium extraction with PPTX XML.

## Product and integration gate

Use an explicit experimental server-side editable mode. Keep the existing image-preserving mode visibly described as non-editable. Show processing and cancellation states, disclose self-hosted processing, hide OCR language controls when OCR is absent, and require review of text, numbers and layout. Do not silently switch to a cloud service or call image-only output editable.

A local standalone adapter now supports `SMARTPPT_EDITABLE_PROVIDER=stirling`, an operator-controlled `SMARTPPT_STIRLING_URL`, and optional `SMARTPPT_STIRLING_KEY`. HTTP is limited to loopback; remote origins require HTTPS. It does not follow redirects, retry conversion POSTs, or send filenames/API secrets to another service; it caps downloaded output and uses the existing PPTX and worker checks. All editable results remain `needs_review`. This adapter is a local prototype, not yet wired into the SmartPDF production website.

Next gate: investigate the 63 text/number-flagged documents, add representative business documents with human truth, validate font delivery and scanned-page OCR, run the pinned Linux core/LibreOffice stack, then integrate through the existing Office task service and run the full website regression suite. Core temporary-file cleanup must be verified separately from deleting the task service's input/output. Cancelling the HTTP client does not prove the native engine computation was cancelled.

## Primary sources

- [Pinned conversion controller](https://github.com/Stirling-Tools/Stirling-PDF/blob/684608d143779bf3a8ffc67639f077a1202c62ff/app/core/src/main/java/stirling/software/SPDF/controller/api/converters/ConvertPDFToOffice.java)
- [Pinned native Office conversion service](https://github.com/Stirling-Tools/Stirling-PDF/blob/684608d143779bf3a8ffc67639f077a1202c62ff/app/core/src/main/java/stirling/software/SPDF/service/OfficeConversionService.java)
- [Official JAR installation requirements](https://docs.stirlingpdf.com/Server/Install/JAR/)
- Existing repository evidence: `docs/m13-stirling-implementation.md`, `config/word-core.stirling-3.2.2.json`.
