# Expanded public evaluation and rejected MacRoman repair, 2026-11-14

Base: `301b7e8c176688db35e9b14dd59aa3d16e8353e2`. No production converter change is included in this investigation commit.

## Fixed new inputs

Six Camelot fixtures were selected before examining outputs: agstat, budget, health, hybrid_multipage, image and missing_values. The manifest binds each to upstream revision 92777b852e00933a5c4b9ba642601784604356cd and Git-blob/SHA-256 identity. These are heterogeneous test resources, not six independent naturally occurring scans: image is an image-only page; hybrid_multipage is a small synthetic table fixture. All six converted with the restored pinned model runtime. Successful export is not an accuracy score.

Independent source-page rendering and directed checks found:

- agstat: 30 regional records plus total; 279 numeric strings matched line-by-line. One header contains a wrongly decoded character.
- budget: 27 numbered records plus department totals; 266 amount/ellipsis strings matched. Plan/Non-Plan grouping and a multiline total heading are incorrect.
- health: 23 state records and 161 numeric strings matched, including real zeroes. The total heading lacks a row merge and the unit label is fragmented.
- image: a manual visual check of the image-only source and workbook matched 12 triples plus one negative value, 37 numeric strings in total. This is one focused scan check, not measured population OCR accuracy.

Other content, blank-cell semantics and header relationships still need broader independent annotations. No evaluation references are fed to the converter; no private documents or original public binaries are committed.

## Reproducible rejected repair

The agstat header uses a nonsymbolic TrueType font with explicit MacRomanEncoding and no ToUnicode. A downstream parser interpreted byte DE as a WinAnsi character rather than the PDF MacRoman fi ligature. A prototype adding the standard encoding map fixed the header's non-whitespace characters on this document, and its MuPDF and PDFium pixels remained unchanged.

[Adobe's PDF 32000-1](https://opensource.adobe.com/dc-acrobat-sdk-docs/standards/pdfstandards/pdf/PDF32000_2008.pdf), sections 9.6.6.4 and 9.10.2, supports character extraction using the named encoding and glyph-name mapping. That does not prove an implementation's rendered input is unchanged when metadata is added. A synthetic unembedded TrueType counterexample accepted by the prototype changed PDFium pixels. The independent reviewer reproduced the failure and blocked the proposed production path. No word-specific replacement, blanket Thorn-to-fi substitution or relaxed test was shipped.

The production source_fonts.py was restored byte-for-byte to the remote baseline. The local rejected prototype and original failed test remain available for research; a standalone counterexample is committed as `probe-macroman-render.py`. It reports the actual before/after pixel hashes rather than pretending equality. Run with the pinned Python environment:

```sh
python scripts/pdf-to-excel/probe-macroman-render.py
```

Observed at scale 2:
- Before: `112adb85e186f340a4d75de4253fb7ba68973179a9fbd038e97b5ab2705e7dcf`
- After: `1ae52f8538f1b6bb4379c0d2b23a992596b0da549fe4b1f379418b2603f54e03`
- `identicalPixels: false`

The regression guard ensures the current production repair leaves this unsupported font and original input untouched. It is not a claim that the character bug is fixed.

## Next safe avenue and limits

A later correction should bind original character codes, font identity and unique glyph geometry to output text without changing the model's raster input, or establish a narrower rendering-safe preprocessing scope across the actual engine chain. Current evidence does not justify a general repair. Budget/health header fixes also need stronger source-backed structure evidence and adversarial counterexamples, not expected-answer hardcoding.

No merge/deployment or general-release claim. Unmodified repository guard remains blocked by 128 existing approved assets absent from the partial checkout; remote assets are preserved. Exact-commit CI and real spreadsheet application acceptance remain unverified.

Local six-file benchmark SHA-256: `5a6bc97c1c525679918466578b3ed3f96f33f05dfd5bc3bd83523b88673c4db0`.

Final cumulative regression: **412 tests run, 411 passed, 1 external Stirling integration skipped**. Independent review approved retaining the failure probe and the unchanged production boundary.
