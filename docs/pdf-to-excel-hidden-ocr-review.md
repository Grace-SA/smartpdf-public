# Read the visible scan instead of trusting an invisible OCR layer

Baseline: `83562978ebc73f41c619614590d43060cccc90a1`.

## Reproduction

An original, generated five-row/two-column scan visibly contains `12.50`, but its invisible PDF text layer contains `19.50`. The two PDFs, with and without the invisible layer, render to exactly identical pixels. The old converter exported `19.50` with both OCR enabled and disabled, reported no OCR page, and gave no OCR warning. Its image-only heuristic had mistaken the existing text layer for trustworthy native content.

The corrected ruled and borderless paths export all ten visible cell values exactly, including `12.50` and `007`. Disabling OCR explicitly refuses the proven scan. A real Tesseract 5.5.0 / Leptonica 1.84.1 PDF generated from the same original scan also exercises this path successfully. These are reproducible recognition/routing tests, not model training or population accuracy measurements.

## Narrow content-stream proof

The classifier is considered only where the previous heuristic would use a text-bearing image page. It admits one ordinary axis-aligned image covering the visible page, with every nonempty text-show operation explicitly under text rendering mode 3. It tracks rendering mode, font and transformation state through q/Q and consecutive Contents streams; BT/ET does not reset text state. Tj, TJ and both quote operators are parsed structurally, not searched as substrings.

Forms, Type3 fonts, annotations, rotation, image masks/embedded alpha, graphics-state changes, path painting/clipping, shading and unknown operators are outside this first subset. Mixed visible/invisible text does not qualify. `other` and `unsupported` are classifier results, not blanket conversion refusals, and neither authorizes throwing away native text. They retain the previous conversion path. This does not detect arbitrary white text, transparency, vector occlusion or all existing OCR formats.

Content decoding is separately bounded: at most 32 streams, 2MiB total decoded content, two filter stages, 64 graphics-stack levels and bounded resources. Only raw, Flate and ASCII85 content without extra decode parameters is accepted. The decoder checks expansion before unbounded decompression and does not mutate global library limits or populate pypdf's decoded cache. The accepted operation count is checked after tokenizing the bounded input; this is not a claim that every other PDF parser or renderer uses only 2MiB.

## Review fixes and routing isolation

Independent review found and fixed missing `/SMaskInData` rejection and a deceptive post-decode byte limit. A 2KB compressed stream previously expanded beyond the limit and remained cached before rejection; it now declines without that expansion/cache. Truncated streams, trailing bytes, unknown filters and cumulative overflow have rejection regressions.

Proven hidden-layer scans bypass native form recovery, the native layout batch, native source-context extraction and native typography. OCR output is explicitly labelled for review. Independent review found another leak in the OCR-layout adapter: a case-insensitive native correction changed correctly recognized `Code` back to hidden `CODE`. OCR adaptation now explicitly disables native text correction and native text-box candidates; the ordinary native adapter remains unchanged. A regression proves that OCR adaptation does not even read native characters or words.

Mixed-document and selection tests verify that only the native page enters the native model, unselected hidden pages are not inspected, and a later OCR-disabled error does not publish a partial workbook or overwrite a prior output. Empty-user-password scans still work; an actual nonempty user password remains an explicit unlock refusal. Sources remain unmodified.

## Validation

- Final pinned-model suite: **374 tests, 373 passed, one external integration skipped**, 91.356 seconds. The external formatter/real endpoint verification belongs to the preceding commit and was not relabelled as a new live run here.
- Twenty classifier/decoder tests and six routing/adapter integration tests pass, including actual ruled and borderless OCR, exact full cell matrices, mixed-page behavior, native-text isolation and encryption handling. The case-isolation test fixes the visual OCR result to isolate adapter behavior; it is not presented as an OCR accuracy test.
- Real Tesseract-generated input exports the same ten visible values, and LibreOfficeDev 26.8 reopens/renders the resulting worksheet without clipping. This is not Microsoft Excel/device acceptance.
- Source-only route review across 68 unique public PDFs checks 140 readable pages, leaving WEB-022 encrypted. Eighteen pages meet the image-plus-text candidate condition; none qualifies as the newly supported hidden-layer subset. All source hashes match. This is a classifier audit, not a rerun of the 68-file conversion benchmark.
- Twelve affected-route public documents were rerun with the final engine, pinned offline models, one worker and the 180-second budget: all twelve converted. Against their respective prior baselines, values/types, merges, sheet dimensions, column widths/row heights, token multisets, comments/authors and result metadata are unchanged. Input and output hashes were verified, and all 48 fingerprinted engine files match the final on-disk version. This targeted subset is not a new 68-file benchmark.

Re-OCR can differ from an existing high-quality OCR layer and is not guaranteed correct. The change stops silently treating a proven invisible layer as visual evidence; it does not establish 100% recognition, cover arbitrary mixed/rotated scans or preserve every semantic background style. No merge, deployment or general-production certification is implied.

Targeted benchmark SHA-256: `959a990b1edf0e1f2b774defa06d3ebdc7f0f6c6a89977f752a8171bbca967e0`.
Canonical comparison SHA-256: `2d2677ed6f012c653a6c7ac2246ac84b173685bd51df836b4cb831fbbbfbc609`.

New-file Ruff checks, critical legacy Python checks and whitespace checks pass. The sparse local repository guard retains the same 129 approved binary-asset absences; no remote binary assets are removed.
