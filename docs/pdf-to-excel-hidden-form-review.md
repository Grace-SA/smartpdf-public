# Bounded hidden OCR Forms

Baseline: `2a57d4444ed445770843cd22bedf9f853caa9a6c`.

## Real software reproduction and synthetic error regression

OCRmyPDF 16.7.0+dfsg1, Tesseract 5.5.0 and Ghostscript 10.05.1 were used locally on an original generated five-row/two-column scan. Both `--pdf-renderer auto --output-type pdf` and `--pdf-renderer hocr --output-type pdf` put invisible Type0 text in a separate Form XObject; the preceding classifier declined these pages. The `auto/pdfa` variant was flattened and already supported. All three PDFs render pixel-identically to the original at PDFium scale 2.

With the extension all three route to visual OCR, mark page 1 as OCR, and export the ten visible cell strings exactly. The original software-generated hidden strings happened to be correct: this experiment proves format/routing coverage, not an OCR accuracy improvement on those inputs.

A separate reproducible integration test places incorrect `19.50` in an invisible Form over the visible `12.50` scan. Conversion now exports all ten visible values, including `12.50` and `007`; disabling OCR refuses without creating an output. Re-recognition is not guaranteed correct on arbitrary scans.

## Conservative proof boundary

Only non-nested text-only Forms are admitted, with explicit resources, a finite positive BBox and absent/identity declared Matrix. Their invocation may inherit the caller's CTM. Every nonempty text show must be under rendering mode 3 with a supported, resolved font. Invisible text alone cannot paint outside the image or through the implicit BBox clip. Paths, clipping operators, images/nested XObjects, shading, graphics-state dictionaries, marked content, transparency groups and unknown Form attributes are rejected.

Form execution inherits the actual resolved font object, not a font resource name that could be rebound by local resources. Its rendering mode, font and CTM are implicitly saved/restored. Page streams and every Form invocation share the existing decoded-byte, stream, operation and graphics-stack budgets, plus a maximum of eight Form invocations. Decoding remains bounded before decompression and does not populate pypdf's unbounded decoded cache. The operation limit is checked after tokenizing bounded content, not a promise of universal PDF resource safety.

Unsupported classification still preserves the previous conversion path; it is not a whole-document conversion rejection or a proof that its native strings are visible. Arbitrary hidden OCR, mixed rotations, opacity and white/occluded text remain outside scope.

## Review and validation

- The 27 classifier tests and new end-to-end wrong-value Form regression pass. Independent review additionally ran eight adversarial checks, including rendered equivalence for all four text-show operators, implicit state restoration, compressed Form expansion/trailing data and nested calls. No new blocking findings remained.
- Ruff checks and formatting pass for all three changed Python files.
- The final source-only audit again checks 68 unique public PDFs and 140 readable pages, leaving the password-protected input untouched. The same 18 image/text candidate pages remain unsupported; the complete classifier audit result is unchanged. This is not a new 68-document conversion run. The preceding commit's 12-document conversion comparison and earlier 22 annotated/46 unannotated baselines are not relabelled as current full conversion validation.
- Real OCRmyPDF input/output hashes and exact cell matrices were checked after the final helper change. The software-generated source PDFs are unchanged. Software output artifacts and models are not committed.

Final pinned-model suite: **382 tests, 381 passed, one external integration skipped**, 100.349 seconds. The unpublished background diagnostic prototype is excluded from this change set and test count. No live external-service test was rerun for this classifier-only extension.

## Remaining fidelity gaps investigated, not hidden

For the public mixed-direction `clockwise_table_2.pdf`, a local physical upright transformation preserved every rendered pixel and native glyph. The converter then exposed a separate layout defect: the model already mixes caption words into first-row numeric cells and misgroups multi-level headers. Therefore the rotation refusal was not merely relaxed. No transformed source or orientation override is shipped.

For the public US-007 semantic gray backgrounds, direct color inference is unsafe: ICC gray interpretation differs from naive component scaling, and masked sampling can miss real shading/painting inside glyph bounds. A diagnostic prototype remains outside this change; no unproved cell fill is applied. These are actual coverage limitations, not claims that the only missing input is private user data.

No merge, deployment, 100% OCR claim or general-production certification is implied.
