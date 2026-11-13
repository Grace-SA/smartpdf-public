# Preserve supported external workbook number formats

Baseline: `2032aea6d480e806204a48181659366317d3ee34`.

## Actual endpoint reproduction

A bounded loopback-only official Stirling 3.2.2 server, using a checksum-verified official Java 25 runtime, exposed four failures in the old adapter. The service returned typed XLSX values with formats, but the adapter discarded significant display notation:

| Source literal | Old adapter | Verified corrected output |
| --- | --- | --- |
| `12.5%` | `0.1` | `12.5%` |
| `01/02/2024` | `2024-01-02 00:00:00` | `01/02/2024` |
| `$1,234.50` | `1,234.50` | `$1,234.50` |
| `(12.30)` | `-12.30` | `(12.30)` |

The same actual fixture also retains `001234`, `123456789012345678` and `1.20`. These seven values were checked through the real HTTP adapter, written to XLSX and reopened as exact literal strings. This is not a mocked endpoint or a native-rotation bypass.

## Restricted fix and review

The adapter now uses a small explicit format subset: fixed decimals, integer grouping, selected literal currency prefixes, percent scaling, positive/negative/zero sections and four unambiguous date-format patterns. Strings remain strings; booleans are not treated as numbers. `General` support is deliberately restricted to canonical short integer value text, not a claim about width-dependent Excel rendering.

Unknown formats, conditional/color/locale directives, scientific/fractional formats, unverified precision, unsupported dates and nonfinite numbers raise an explicit conversion error. Dates before 1900-03-01 are refused because the Excel serial-60 calendar ambiguity cannot be recovered after parsing. Unsupported cases do not silently fall back to `str(value)`.

Review found that negative nonzero values rounding to zero have different display behavior across format sections. A real LibreOffice XLSX-to-PDF probe confirmed the difference, so this subset refuses nonzero values that round to zero rather than inventing a sign. Independent review also reproduced inherited Decimal exponent/trap settings changing behavior; isolated Decimal contexts and a regression now prevent caller-local context leakage.

## Irreversible upstream ambiguity

WEB-010 contains parenthesized sample-size-marked values, including `(0.0)`. Stirling has already converted those zeros into numeric `0` with only a negative-parentheses section. The original zero notation cannot be reconstructed from that workbook. The adapter therefore refuses numeric zero with a negative-parentheses format. This intentionally also declines otherwise legitimate accounting-style zeros until source geometry can resolve the ambiguity. It does not guess parentheses or silently export a changed value.

The actual WEB-010 direct adapter and full conversion pipeline both refuse with the specific ambiguity reason. The full pipeline was verified to call the real adapter once, leave no XLSX behind and leave the source hash unchanged. Refusal is correct risk handling, not successful table reconstruction. The external engine's mixed-direction header grouping remains imperfect and is not fixed by a display formatter.

## Validation and limits

- Published-change-set suite: **348 tests, 347 passed, one genuine external integration skipped**, 88.658 seconds. The newly added hidden-OCR work is a separate unfinished change and was excluded from this checkpoint.
- The skipped direct external integration passed separately against the real server. Real seven-literal conversion, final workbook reopening, and WEB-010 direct/full-pipeline expected refusals also passed.
- Ten formatter tests and eight offline adapter-contract tests pass. The latter generate their own PDF/XLSX inputs, check exact endpoint/multipart fields/selected page, preserve merged table structure and verify formula-looking content stays string data with no executable formulas or external links.
- Full Ruff checks pass for the new files; critical legacy Python and whitespace checks pass. The repository guard retains the same 129 approved binary-asset absences in the sparse local index.
- The 68-file regression at the baseline commit remains separately documented; it was not rerun or relabelled as this version. This change is confined to the external adapter, whose real route was tested directly. No population accuracy, full external structural fidelity, Microsoft Excel/device acceptance or production readiness is claimed.
- Each test service was stopped and its process exit verified. No deployment or repository service configuration changed. A short client timeout does not prove production backend cancellation/retention; that remains a separate acceptance requirement.
