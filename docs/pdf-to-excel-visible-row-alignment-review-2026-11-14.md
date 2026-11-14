# Native split-row integrity repair, 2026-11-14

Base: `eef241f69fb67fbc75d5861925a5ff84fc222b0b`, `feature/pdf-to-excel`. This is a narrow correction in the existing native-table path, not a new UI, OCR engine, release, merge or deployment.

## Reproducible public failure

The public [Camelot diesel-engines fixture](https://raw.githubusercontent.com/camelot-dev/camelot/92777b852e00933a5c4b9ba642601784604356cd/tests/files/diesel_engines.pdf), SHA256 `6675404fa9f9cd8fb9d34d9d73056fe8e4823519adab13e8b91233d667ffd13c`, page 11, contains a clearly ruled monitoring table. The source's temperature label and its `local` indication occupy the same physical row and native text baseline. The prior model placed the label at A13 and the indication at D14, leaving D13 empty and producing a nameless following record.

The native grid is 30×8, whereas the model output was 29×9. Existing native-preference logic intentionally requires matching dimensions, and the dense-grid fast path excludes merged grids. Neither guard is removed. Whole-table replacement would also conceal unrelated split-column and mixed-subrow defects, so this change repairs only the individually proved adjacent-row split.

Source fixture identities, including seven newly investigated public documents, are in `scripts/pdf-to-excel/row-alignment-public-manifest.json`. PDFs, extracted page images and converted workbooks stay local; these upstream research fixtures are not approved for redistribution in this repository.

## Bounded recovery conditions

- Adjacent model rows must have disjoint occupied columns, single-row spans and at least two nonempty cells. Crossing spans and meaningful empty merged cells decline recovery.
- Every value must uniquely match an entire cell in one complete closed native row, with no missing source value, new text, duplicate glyph ownership or alternative native owner.
- Actual native glyphs, not merely model boxes, must share one baseline within 0.5pt. Candidate text is restricted to known opaque black DeviceGray/RGB/CMYK glyphs with no significant overlap; 0.05pt accommodates subpixel font-spacing noise.
- Native boundaries must also be visible, contrasting lines in the final rendering. Images, annotations, filled obstacles, intersecting line/curve paint and unsupported drawing states decline recovery.
- A bounded stream check excludes clipping, Forms, optional-content constructs, unknown graphics state, nonzero text rendering modes and non-unit linear CTMs. Translation is allowed; arbitrary CTM stroke-width conversion is not claimed.
- A copied page must render exactly like the source. A second rendering with text-show operators removed supplies text-contribution evidence, rather than treating unrelated ink inside a glyph box as proof. This is combined with opaque black text, unique ownership, overlap and paint-intersection checks; the global difference alone is not a per-glyph visibility proof.
- The unchanged model is returned when proof is unavailable. Native rows/columns and nonempty strings are bounded; actual comparison work is capped, stream decoding uses the existing 2MiB/20,000-operation guard, and rendering is capped at 20 million pixels. No new package, network service or model download is introduced.

Only row indices and inferred row heights change. No nonempty string is rewritten or inferred, and the before/after nonempty-text multiset must be identical. No sequence guessing, sample-name check or expected-value special case is used.

## Review and verification

Independent review found and drove fixes for multiline boxes masquerading as one baseline, invisible rules, transparent/white text borrowing unrelated ink, overprinted glyphs borrowing other text, partial white-stroke occlusion and scaled strokes understating their painted extent. The corresponding self-contained synthetic PDF tests are retained.

The configured cumulative suite completed **481 tests: 480 passed, one external-Stirling test skipped**. A preliminary run without the required model-directory setting was not acceptance evidence: a scanned-borderless test failed and two tests skipped. With the existing verified model directory configured, the final suite passed as above.

Independent actual conversion of public page 11 confirmed **29×9 → 28×9**: old rows 13 and 14 become new row 13; later rows shift by one. Every nonempty value, data type, mapped cell position, mapped merged range, column width and the complete nonempty-value multiset matched. A13 and D13 now belong to the same record.

The final XLSX's total displayed row height is not conserved: the previous two rows each hit the existing 20pt minimum, whereas the combined row also hits that minimum. No claim of an Office-rendered visual acceptance run is made.

The frozen public assessment covered **58 SHA-deduplicated PDFs: 54 exported and four retained their previous refusals** (two mixed/rotated-table cases, the nested-label case and the Senate rotated-table case). Comparing all 54 exported workbooks with their frozen references found only the page-11 change described above. The other 53 matched in cell values/types, dimensions and merged ranges; this is not a byte-for-byte or Office-formatting comparison.

After that corpus run, one final exception-only patch added the precise `MalformedPDFException` wrapper to the optional rendering fallback. The cumulative 481-test suite was rerun on the final code (480 passed, one skipped), and independent real page-11 conversion plus the 15 focused tests were rerun successfully. **The final hash was not rerun across all 58 PDFs.** The corpus evidence and final-code evidence are deliberately distinct. The only engine hash change after the corpus run was `source_row_visibility.py`, from `90ba0763b4751a0cb70a380413bba6cf84c7afe5ea098cd050ec837fa6215add` to `ee27c3e622fc5f5273ed5dfdee52c27e04e9797495303bde6cb4956b54f6713d`; it adds that exception import/catch without changing the successful-recovery algorithm. The specific new exception and stream restoration are covered by the final focused test.

## Remaining limits

This does not make the whole source table correct. The Turbocharger label is still split across columns, and an `L LL` entry still mixes source subrows. Source-grid 30×8 versus output 28×9 is not an exact structural match. The repair also intentionally declines colored text, ambiguous source ownership, complex graphics and unsupported transformations. Successful export counts are not accuracy rates or proof of general production readiness.

`node scripts/check-repository.mjs` was run and remains blocked by 128 approved assets absent from this partial local index. All 128 were verified present in the unchanged remote base tree. Publication must preserve that base tree and add/update only the explicitly reviewed text files; no binaries or private documents are added or deleted. This limitation is not reported as a passing repository check.

No merge, production release or deployment is authorized by this review. CI status for the eventual commit must be reported separately; local test success is not CI success.
