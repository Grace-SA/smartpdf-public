# PDF-to-PPT quality round 13: reproducible Linux base-font rendering

## Scope and root cause

The two round-12 Linux real-render regressions used unembedded regular Helvetica. PDFium renders this with its built-in ChromSansOTF outlines; substituting Office Arial/Liberation Sans changes glyphs, notably numeral `1`. Matching advance widths alone was insufficient. Calibration, translation and a Nimbus alias were evaluated and rejected because they did not pass the existing pixel gates.

This change selects `SmartPDF Base Sans` only for exact unembedded Helvetica regular, matching a reviewed 15,025-byte built-in CFF SHA-256 (`a02339e95d20db14cbdfc1c6baf359cd36a091d5434925c3a4040f60e1a1af9e`). Embedded fonts, different names/bytes, bold, italic/synthetic shear, and unsupported raw or NFKC characters keep the previous path. It does not copy or store uploaded fonts.

## Provenance and portability

The pinned bytes were compared byte-for-byte with the PDFium FoxitSans source:
https://pdfium.googlesource.com/pdfium.git/+/refs/heads/chromium/3347/core/fxge/fontdata/chromefontdata/FoxitSans.cpp

The full PDFium BSD license and original Foxit copyright are included in source, wheel package data and generated font metadata. Generation uses a synthetic PDFium standard-font loader and rechecks the source hash. The reviewed 1000-unit font matrix is checked; vertical metrics derive from the CFF bounds. fontTools 4.68.0 converts cubic outlines with maximum error 0.1 font unit. Fixed metadata/timestamps make repeated generation byte-identical. The full face is embedded, not a text subset. Rendering materializes the exact TTF bytes placed in the EOT font payload.

No binary font or private sample is added to GitHub. Pinned source mismatch fails closed for explicit embedding; optional source selection retains the existing route.

## Review and verification

- Independent review caught a missing wheel license declaration and raw combining-character coverage not guaranteed by NFKC alone. Both fixed with regression tests.
- New base-font tests: 19 passed, including tamper/style/source rejection, regenerated-byte determinism, identical renderer/EOT bytes, license packaging and actual LibreOffice post-embedding font identity/text.
- Previously failing real-render modules: 20 passed, including regional extension rollback and sparse regional recovery.
- Wheel built successfully and extracted package generated the approved font without source-checkout resources (39,180-byte TTF, SHA-256 `8086e8934f56c4f1780d847189e11cd9081636f2ec91cb477db68bd211ff30a6`).
- Full existing suite with actual LibreOffice renderer and pinned Noto/CMU fonts: **516 passed, 24 skipped**, 249.35 seconds. Skips require Mac-installed proprietary font evidence. The 19 new tests ran separately after collection, giving **535 distinct passing tests**, not a claim that skipped environments passed.
- Independent portable-font recheck: 8 passed, including both actual CJK embedding cases.
- All existing content, numeric, regional pixel and whole-page gates remain unchanged.

## Remaining release evidence

This is a narrow repair, not universal launch certification. Windows PowerPoint/WPS/Mac rendering, broad real-document regression and the prior frozen private corpus still require their own evidence. The local checkout is text-only; repository hygiene checking reports the same 129 approved binary assets absent from its index, not source errors. Publication preserves all other remote blobs. GitHub Actions quota remains exhausted; local test evidence is not represented as green CI. No merge or deployment is performed.
