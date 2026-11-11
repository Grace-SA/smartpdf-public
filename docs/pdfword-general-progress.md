# PDF to Word reconstruction development

Base: `72a14941862587b60c6c7c3d0a159f90b461a1dc`. Feature branch: `codex/pdfword-general`.

Status: local acceptance candidate. The two approved batches are **not yet accepted for general production**. The existing pinned Docker runtime remains on the frozen v1 converter. Setting `PDFWORD_LOCAL_V2=1` explicitly selects the new local reference runtime; shared production mode rejects this runtime. Do not promote the existing image pin to imply that OCR is deployed.

## Implemented

- Schema 2 separates bounded page geometry, ordered content, paragraphs/runs, tables/cell spans, header/footer and visual regions from engine outputs.
- Native extraction reconstructs paragraphs, basic styles, original list ordinals, reading order and ruled tables. Ambiguous numeric rows and incomplete grids request OCR rather than silently flattening tables into prose.
- Repeated sparse text grids also request OCR. A real borderless-table probe exposed the previous numeric-only routing gap; the regression now checks editable cells after routing.
- Native/scanned/mixed/hidden-text pages route independently. Hidden OCR text is replaced by recognition of the visible page. Unmapped glyphs, rotation and meaningful clipping trigger OCR. Images and formula regions are retained from the page raster.
- OXR uses its full layout and regional recognition pipeline. U2 has a bounded structured-output adapter. Paddle uses its official layout pipeline and a local MLX recognition endpoint. Whole-page text recognition is not presented as table reconstruction.
- Paddle orientation correction can prepare the OXR/U2 input. Photographic unwarping is opt-in with `PDFWORD_PADDLE_UNWARP=1`; it is not applied indiscriminately to every scan.
- Cross-page tables merge only with compatible geometry and explicit continuation or repeated-header evidence. Repeated data rows are not automatically marked as headers. Word pagination may reflow.
- Editable DOCX export preserves source-page bookmarks, merged cells, images and inline styling. An independent Node OPC validator verifies ZIP integrity/budgets, relationships, XML, PNG payloads and page/table/image counts against the conversion manifest.
- Page progress, OCR review warnings, actual server capabilities, capability-aware FAQs and the three technology credits are in the UI. OCR results say they are ready for review.
- Cancellation, bounded OCR subprocesses, local temporary directories and atomic final output are retained. The local reference job has a 270-second budget, individual OCR calls 180 seconds, and a cumulative raster budget. The UI's 200-page maximum is an input limit, not a guarantee for 200 scanned pages.
- Both layout and Paddle recognition endpoints are restricted to loopback. Inline mathematical markup that is not rendered as an equation is explicitly reported for manual formatting.

## Local setup

The CPU converter uses `server/pdfword/requirements-v2.txt`. OCR environments are separate from that environment. Local testing used MLX-VLM 0.7.12, MLX 0.32.4, PaddleOCR 3.5.0 and PaddlePaddle 3.3.1. OXR layout detection runs separately on loopback. Model artifacts and their local manifests are not product source files.

Set `PDFWORD_OCR_PYTHON`, `PDFWORD_MODEL_ROOT`, `PDFWORD_PADDLE_PYTHON`, `OXR__LAYOUT_ANALYZE_MODEL__URL` and the upstream OXR `PYTHONPATH`. Model subdirectories are `u2`, `oxr`, `paddle-vl`, `paddle-layout`, `paddle-orientation` and `paddle-unwarp`. Paddle regional comparison additionally needs its local `PDFWORD_PADDLE_URL` OpenAI-compatible endpoint. Production provisioning is a separate unfinished gate, not an implicit fallback to this host process.

Use the repository's licensed Noto Sans SC font when rendering CJK acceptance documents. The bundled minimal LibreOffice environment needs an explicit local fontconfig profile; XML text checks alone do not establish visible CJK rendering. Font substitution in Microsoft Word remains part of real Word acceptance.

## Evidence and limitations

Downloaded public PDFs, images, source URLs, hashes, converted files, rendered pages and exact evaluation inventories are **local only**, outside the repository. No downloaded document is a checked-in fixture or a CI attachment. Synthetic regression fixtures keep their identities; v1 expected refusals are tested separately from v2 improvements.

The current local run has verified source markers on all 13 supported synthetic cases and the combined case, preserved double-column reading order and converted the synthetic two-page continuation into one editable table. Encrypted, malformed and over-limit fixtures still refuse without partial output. Real browser upload, OCR, DOCX download and deletion passed against the actual local service at a 390-pixel viewport, including all three technology credits.

Independent upstream text references exposed both strengths and failures: one clear English image matched exactly, a European multilingual page had about 0.29% whitespace-normalized CER, and a lower-quality historical scan had about 3.63% CER. These are development probes, not a representative accuracy claim. Paddle alone duplicated a sentence on a rotated sample; the automatic orientation-correction plus OXR route matched that sample's reference exactly after correction. This does not establish general photo accuracy.

The broad native-only probe intentionally runs without OCR, retaining all refusals. Its generation count must not be quoted as overall product acceptance. Selected real OCR probes cover scanned tables, cell spans, historical scans and image/text combinations. Their generated status is still distinct from cell-by-cell ground-truth acceptance.

The local download inventory contains 139 files with 137 distinct hashes and 912 readable pages/images, plus three recorded download failures. These are not 137 proven independent source families. The final native-only probe generated 31 review candidates, refused 105 and could not open three. Two misleading language filenames were corrected in metadata after content inspection. Selected Chinese and Japanese pages render with the supplied CJK font; Japanese ruby/reading order and inline mathematics still require further work.

Local cumulative verification: 75 Vitest files / 629 tests passed; 23 Python checks passed; TypeScript and build passed. The cumulative browser suite reported 638 passed, four skipped and four WebKit navigation failures. The same four failures reproduced against an untouched archive of the exact baseline commit. No tests were relaxed to hide them. The PDF-to-Word browser tests and real local OCR service flow passed. GitHub CI for the eventual commit remains separate evidence.

`python server/pdfword/acceptance.py <local-evaluation.json>` is a separate fail-closed release gate. It requires the agreed independent corpus size, per-category coverage, frozen held-out sources, accuracy/structure/reading-order metrics, editing and visual checks, performance and platform evidence. It currently fails. Samples already used for development must not be retroactively relabelled as clean held-out evidence.

## Remaining work before general release

1. Complete per-cell/reading-order annotations and a genuinely frozen held-out corpus, including at least ten independent sources per core category. Resolve the observed poor-scan errors and validate complex borderless/cross-page tables quantitatively.
2. Finish layout fidelity for multi-column, nested, overlapping and complex mathematical content; current output prioritizes editable reading order and may reflow columns into one flow. Lists retain source numbering as editable text; they are not yet fully reconstructed semantic Word numbering definitions. Image/table fallback does not equal full editability.
3. Validate Japanese, unusual font mappings, annotations, full photographic distortion coverage and long mixed documents. Passwords, active forms, visible annotations and unsupported page geometry remain explicit boundaries.
4. Build and pin an isolated Linux GPU worker, then validate concurrency, memory, cancellation/cleanup and ten-page warm P95 budgets. The Apple Silicon reference adapters do not meet that deployment requirement by themselves.
5. Open, edit, save and rerender the accepted corpus in actual Microsoft Word. LibreOffice and python-docx reopening are useful independent checks, not Microsoft Word acceptance.
6. Pass final exact-commit CI and review the feature branch before merge. Production publication requires separate authorization.

## Primary references

- [SoMark OXR](https://github.com/SoMarkAI/OXR)
- [Unlimited-OCR-2](https://huggingface.co/baidu/Unlimited-OCR-2)
- [PaddleOCR-VL official pipeline](https://www.paddleocr.ai/v3.5.0/en/version3.x/pipeline_usage/PaddleOCR-VL.html)
- [Paddle document preprocessing](https://www.paddleocr.ai/v3.5.0/en/version3.x/pipeline_usage/doc_preprocessor.html)
- [PaddleOCR-VL 1.5 MLX weights](https://huggingface.co/mlx-community/PaddleOCR-VL-1.5-bf16)
