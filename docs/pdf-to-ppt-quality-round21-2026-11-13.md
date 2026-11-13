# PDF-to-PPT round 21: prove page-unit quantization, then retain visual refusal

## Decision

This round adds an **offline diagnostic**, not a new production acceptance path. The default multi-resolution guard and converter remain unchanged. A geometrically explained page-size discrepancy does not prove that a font substitution or moved word is visually safe. The W-9 experiment demonstrates exactly that distinction.

## Units and model

LibreOffice imports `sldSz` through [presentationfragmenthandler.cxx](https://github.com/LibreOffice/core/blob/master/oox/source/ppt/presentationfragmenthandler.cxx), [drawingmltypes.cxx](https://github.com/LibreOffice/core/blob/master/oox/source/drawingml/drawingmltypes.cxx) and [unit_conversion.hxx](https://github.com/LibreOffice/core/blob/master/include/o3tl/unit_conversion.hxx). The positive-value unit conversion rounds to the nearest hundredth of a millimetre, half upward:

- 1 point = 12,700 EMU; 1 hundredth millimetre = 360 EMU.
- `mm100 = (actual_slide_emu + 180) // 360`.
- `expected_pdf_points = mm100 × 360 / 12700`.

The actual PPT integer dimensions are required. They must match the producer's existing `Pt(PDFium_float32_dimension)` integer-truncation rule. The tool does not guess the PPT dimensions by rounding a PDF decimal or choose whichever floor/nearest model happens to fit. The PDF output must equal the single expected 12-decimal half-up serialization observed in this runtime, within its 0.0000000000005pt representation bound. This is not permission for any arbitrary difference below a tolerance.

For W-9 the actual PPT is 7,772,095 × 10,057,993 EMU. The original PDF is 611.976 × 791.968pt; the raw Office export is 611.971653543307 × 791.971653543307pt. Both exported dimensions match the documented unit model. The 12-decimal serialization is a deliberately narrow observed-runtime contract, not a claim that every LibreOffice version/page size uses that format. Other serialization forms are refused. Using floor instead of nearest gives the wrong height and is explicitly rejected.

## Proof and safety boundaries

`canvas_quantization.prove` is pure and returns a geometry explanation, never visual permission. It requires:

- Original PDF numeric values preserved as decimal tokens, not rounded through a Python float. An independent review caught that `pypdf.FloatObject` and its display representation lose precision: the apparently six-decimal Office values were not the original tokens. Both child-local numeric parser paths now preserve bounded literal tokens and self-test that precision; unsupported parser paths refuse. The old six-decimal approximations are explicit negative tests, not an allowed fallback.
- MediaBox equals CropBox, with zero origin, unit scale 1 and rotation 0 for all three PDFs. Unsupported crop/origin/unit conventions are refused, not normalized.
- Raw source dimensions agree exactly with PDFium's float32 representation used by the producer.
- Previous and candidate raw dimensions are equal and satisfy the single EMU conversion model.
- Source/raw/output grids have the same ceiling pixel dimensions at 144/216/288/432 DPI, calculated with exact rational arithmetic. Arbitrarily small positive raw-decimal changes across a pixel boundary must remain visible; ambient Decimal precision cannot round them away.
- Both source boxes and fixed integer-point, 1pt-padded ROIs remain within the source and quantized page. No hidden clipping at a fractional page edge.

`public-native-quantization.py` snapshots regular files with size limits. PDF/PPT metadata parsing runs in a child with wall/CPU/address-space/output bounds; PPT XML has size, count and entity/declaration checks. Original PDF numeric tokens are retained in that child, and unsupported numeric constructions fail closed. No parser override reaches the parent or production converter.

Only after proof does the tool render the three immutable PDFs. It uses unchanged fixed-coordinate Poppler pixels and the existing local MAE, foreground MAE, ink-edge error and exact previous-to-candidate outside-ROI checks. It does not transform, rescale, translate, register, crop away a discrepancy or mutate a PDF's page boxes. Each output explicitly says `diagnostic_only: true` and `production_acceptance: false`, even when all diagnostic measurements are nonregressing.

## Real sample outcome

The previously rejected W-9 −0.2pt experiment contains four additional words, 21 source positions: `W-9`, `resident`, `3.`, `interest`. Its embedded actual text and ordered numbers match the candidate textboxes, without source-extra numbers. The strict default guard still refuses its page dimensions.

The final token-preserving diagnostic produces 16 region/resolution samples. All four words still fail at least one unchanged multi-resolution visual criterion: foreground error increases on `W-9`, `resident` and `interest`; `3.` has an uncertain ink border at every tested resolution. The old source/retained error is reported rather than subtracted. Thus page quantization was a diagnostic barrier, not the sole underlying quality problem. None of these 21 positions is added to production, and no general-release or recovered-editability claim is made.

The same bounded raw-metadata geometry proof was checked against the existing final round-20 artifacts from the fixed eight-page public corpus (not a new conversion run): the three W-9 and four paper pages satisfy the model; the dummy PDF is correctly refused because at least one ceiling pixel grid differs. No resampling is used to make it pass. This seven-of-eight result is geometry-only and does not certify text or editability.

## Verification

Observed environment: LibreOfficeDev 26.8.0.0.alpha0 (`2c87e51eeaa2b413ff4ae097b2705eea1995d8e5`), Python 3.12.14, pypdf 7.0.1 and PDFium 159.0.8149.0. The child-local parser hooks self-test both numeric paths; a future incompatible parser is refused rather than silently using float-derived metadata. This is not cross-version or Microsoft Office certification.

Final cumulative regression: **917 passed, 24 skipped**, one upstream Starlette deprecation warning, 411.46 seconds. The existing skipped Mac-specific prerequisites remain unavailable. The final 60-test focused set includes actual Office rendering, raw-token precision attacks, exact rational grid boundaries, ambient decimal precision/traps, resource limits, XML refusal and strict default-guard preservation.

The final exact-arithmetic implementation was rerun on the actual embedded W-9 candidate: geometry is proven, all four candidate ROIs fail visual nonregression across 16 recorded observations, and production acceptance remains false. A fresh call to the unchanged default guard still returns `page_dimensions_differ`. The production guard, recovery pipeline and word-cluster modules are byte-identical to round 20. No new eight-page conversion is claimed; the separate eight-page geometry audit uses the previously verified final artifacts.

Wheel SHA-256: `c928fda091bdf7f721112c28afc0baff44ab909f76ea73500f3316bd7e65cb3e`; its model module matches the reviewed source byte-for-byte. The repository checker reports only the same 129 approved assets absent from the sparse index, with zero other findings. All non-whitelisted remote blobs are preserved at publication. Public PDFs, fonts, rendered images and temporary candidate decks remain outside Git.

## Remaining work

Small-font shape/spacing fidelity on dense documents remains unresolved. Read-only inspection of W-9 page 2 identifies four embedded HelveticaNeue LT Std Type1C/CFF subsets (51–81 glyphs, WinAnsi encoding, no ToUnicode). Copyright/trademark notices do not establish permission to convert and embed them as editable PPT fonts, and no applicable permissive license or editable-embedding permission was verified. The subsets are not automatically extracted, converted or redistributed; both permission and incomplete editing character coverage remain open. Correct geometry cannot justify a failed visual substitution. Existing round-20 production coverage remains unchanged. Microsoft Office parity, the unavailable private corpus, service/load validation and scans/OCR remain separate open requirements. GitHub CI is not substituted by local results; this work is neither merged nor deployed.
