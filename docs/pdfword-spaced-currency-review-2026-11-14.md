# Spaced currency fidelity follow-up

Base: `eb338db9a5067efaf74eb0e96688806698d2c37f`, branch `codex/pdfword-general`.

## Reproduction

A generated native PDF (ReportLab Helvetica 12, 612 x 792 pt, text at 40,720)
containing `Total $5+$ 10=$ 15.` converts successfully without warnings at the
base commit but its DOCX contains one OMML equation `5+` and ordinary text
`Total  10=$ 15.`. Two dollar signs are silently lost. No source images or
private data are required. The native-PDF test regenerates the input.

A fully spaced `Total $ 5 + $ 10 = $ 15.` reproduces the parser-level problem
but not the original native-PDF converter problem because that extractor
splits it into separate runs. The regression covers both, without conflating
their evidence.

## Change and boundaries

Within the current logical text block, ignore leading Unicode whitespace
(including newlines) when checking the next numeric amount after a
single-dollar pair, as already done for the first amount. Retain the original
paragraph text, including every space and symbol; do not rewrite numbers or
reconstruct content. Existing paragraph-level protection propagates to styled
runs. Cells and paragraphs remain independent. Explicit math delimiters remain
available.

This deliberately preserves ambiguous `$5+5$ 10 units` literally; it does not
claim to infer author intent. Valid `$5+10$ units`, `$5+10$ + 10`, ordinary
single-dollar math, explicit math and unsupported-math fallbacks are tested.
Space, tab, NBSP and narrow NBSP plus signed amounts are parser regressions;
only ordinary spaces are claimed as native PDF end-to-end evidence.

## Verification

- Full Python suite: 196 tests, 193 passed, 3 existing optional scan-quality
  skips, 6.273 seconds.
- Real native PDF to DOCX: exact editable text, zero OMML and zero images for
  the currency inputs. Existing math export tests remain passing.
- Independent review: 9 focused tests passed in 0.256 seconds; no blocker.
  Reviewer confirmed the ambiguity and Unicode-whitespace scope above.
- Office visual rendering and real Docker acceptance remain unavailable;
  this change does not introduce a layout algorithm. No merge or deployment.
