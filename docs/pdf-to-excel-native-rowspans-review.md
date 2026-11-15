# Native header rowspans and a second preselected cohort

Baseline engine: `5a41ad1a9f16b9f1d4cca839289c89fdd71e10b4`.

## Narrow recovery and safety review

US-001 page 3 has a native `Difference` heading in one closed physical cell crossing two header tiers, but the model places its text in the lower tier only. Source rules and neighbouring header baselines prove the intended rowspan. Recovery requires a unique closed native rectangle, repeated body-column anchors, an empty upper slot, full matching native glyph content, a single shared separator in adjacent columns, no internal separator in the candidate, and no overlap with any annotation. It moves the existing literal text without changing row count or body values.

The other `Difference` heading is represented by a visible PDF FreeText annotation appearance rather than native page glyphs. That case remains unchanged. The helper does not treat a model string, annotation Contents field or test reference as proof of rendered native content.

Independent review constructed real FreeText appearance streams with empty and missing Contents fields. An initial annotation check would have permitted an unsafe merge through that visible text. The final gate rejects every overlapping annotation regardless of Contents/AP metadata. Unknown or malformed annotation geometry causes this optional recovery to decline. Review also found malformed edges/native rectangles and geometry extraction failures that could throw exceptions or bypass checks; finite ordered geometry, explicit work budgets and a narrow expected-geometry exception boundary now retain the original model result. No partial mutation is applied.

## Broader preselection, not a population claim

A second cohort was chosen by the fixed ranges EU007–012 and US007–012 before conversion results were inspected. The pinned source has no canonical eu-009 or us-011 PDF/annotation pair; their a/b metadata was recorded and the two entries excluded without quality-based replacement. The remaining ten pairs comprise 31 pages. All twenty PDF/XML files were verified against official pinned Git blob identities and local SHA-256 hashes.

`prepare-icdar.py --manifest scripts/pdf-to-excel/icdar-next-public-manifest.json <directory>` reproduces this second selection. The original twelve-file default remains unchanged. Complete manifest preflight rejects duplicate/invalid IDs, paths and blob identities before downloads. Source PDFs, labels and generated workbooks are not redistributed.

The second baseline exports 10/10 files but is not perfect: 928/951 position-normalized text matches, 943/951 row-aligned normalized matches and 939/951 row-aligned normalized text-and-span matches. Source review distinguishes actual reading-order/layout gaps from annotation conventions and source content outside the annotated table. In particular, additional source fee calculations are not hallucinations and must not be deleted merely to match a smaller annotation region.

## Validation

- Final tested-change-set regression: **302 tests, 301 passed, 1 skipped**, 88.594 seconds. The external Stirling integration remains skipped. Seven new rowspan tests include real empty/missing-Contents appearance streams and malformed geometry; the preparation suite has eight tests. Independent review reran all earlier failing cases successfully. New code passes full Ruff; modified legacy integration passes critical checks; whitespace checks pass.
- Frozen actual conversions cover **22 PDFs / 70 pages** in two separately bound cohorts. All 22 export before and after, with **no strict or aligned regression** in either cohort. The original twelve-file cohort improves by exactly one native header: normalized text at position **2,546 → 2,547 / 2,548**, normalized text-and-span **2,545 → 2,546 / 2,548**, and matched annotated merged cells **36 → 37 / 38**. All second-cohort metrics remain unchanged.
- Direct workbook inspection confirms the only position/merge change across 22 files is `Difference` moving from F3 to F2 with a new F2:F3 merge on US-001 page 3. Literal string/type multisets, source-context comments, table dimensions and numeric values are preserved. The annotation-backed K heading remains unchanged. Both final engine fingerprints match the recorded benchmark hashes.
- LibreOfficeDev 26.8 reopened and rendered US-001. The recovered native header spans the two tiers without clipped text; source-backed column widths remain unchanged. This is a compatibility smoke check, not Microsoft Excel/device acceptance or pixel-identical layout certification.
- Repository guard remains blocked only by the same 129 approved binary assets missing from the sparse local index; no remote assets are removed. Optional historical table-count-reference checks remain explicitly unverified. Only code, original synthetic tests and public provenance/aggregate evidence are committed. This is not general production certification. The two cohorts do not establish broad multilingual, natural-scan or Office/device compatibility. The GitHub CI allocation issue remains separate from local test evidence. No merge or deployment.

Local aggregate comparison SHA-256 values:
- Original twelve-file cohort: `dfb7953aab52a2aa6bb81ee47fa67acef5854b42b8852cc642eb592496196610`.
- Second ten-file cohort: `2e1a73b470e7ab312658d700f30ea4b9f0df212bf0e8280d046dceb8b3e9861b`.
