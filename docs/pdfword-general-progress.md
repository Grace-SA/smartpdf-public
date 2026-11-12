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
- Both layout and Paddle recognition endpoints are restricted to loopback. A bounded, non-executing LaTeX subset now exports editable Office Math: fractions, roots, sub/superscripts, common operators and Greek symbols. Unknown syntax remains visible and is reported for manual formatting. Display-formula image regions remain images.
- Conservative geometric bands now produce real two/three-column Word sections with full-width headings. Column breaks precede the next paragraph, avoiding a spurious blank first line in the right column. Overlapping or ambiguous layouts keep reading flow instead of forcing an incorrect column grid.
- Automatic OCR can retry a rejected OXR result through U2 when both local models are installed. It restores original pixels before the retry, shares one 180-second page budget (120 seconds for the first attempt), preserves cancellation, and validates the alternative structure before exporting it. A retry warning remains visible; structural recovery is not a recognition-accuracy guarantee.
- U2's unclassified `other` text is preserved as an editable paragraph. Empty/unreadable/image placeholders and embedded table markup are still refused; unrecognized classes from other engines are not broadly accepted. The full benchmark was restarted after this adapter coverage fix, with the earlier partial run archived separately.

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
2. Finish layout fidelity for four-column, nested, overlapping and complex mathematical content; ambiguous layouts still prioritize editable reading order and may reflow into one flow. Lists retain source numbering as editable text; they are not yet fully reconstructed semantic Word numbering definitions. Image/table fallback does not equal full editability.
3. Validate Japanese, unusual font mappings, annotations, full photographic distortion coverage and long mixed documents. Passwords, active forms, visible annotations and unsupported page geometry remain explicit boundaries.
4. Build and pin an isolated Linux GPU worker, then validate concurrency, memory, cancellation/cleanup and ten-page warm P95 budgets. The Apple Silicon reference adapters do not meet that deployment requirement by themselves.
5. Complete corpus-wide real Microsoft Word acceptance, distinguishing edit/save/reopen/export compatibility from visual fidelity. The eight focused Word for Mac 16.115 probes pass the compatibility operations, but complex mixed-layout probes still reflow. LibreOffice and python-docx reopening are useful independent checks, not Microsoft Word acceptance.
6. Pass exact-source Linux verification and review the feature branch before merge. The user has now authorized AWS testing and eventual publication, including the documented local-equivalent CI route while GitHub Actions is blocked by account billing. This authorization does not waive the quality, privacy, isolation or rollback gates.

## Primary references

- [SoMark OXR](https://github.com/SoMarkAI/OXR)
- [Unlimited-OCR-2](https://huggingface.co/baidu/Unlimited-OCR-2)
- [PaddleOCR-VL official pipeline](https://www.paddleocr.ai/v3.5.0/en/version3.x/pipeline_usage/PaddleOCR-VL.html)
- [Paddle document preprocessing](https://www.paddleocr.ai/v3.5.0/en/version3.x/pipeline_usage/doc_preprocessor.html)
- [PaddleOCR-VL 1.5 MLX weights](https://huggingface.co/mlx-community/PaddleOCR-VL-1.5-bf16)
- [Microsoft Word LaTeX and Office Math](https://learn.microsoft.com/en-us/office/math/latex)

## Follow-up acceptance methodology

The local whole-file benchmark freezes converter source and hashes each input/output. It runs all 139 inventory entries with OCR enabled, applies the same 270-second local task budget, independently validates the generated DOCX and source-page markers, and verifies a programmatic edit/save/reopen. Failed or explicitly refused files and timeouts remain in the denominator. Image entries are wrapped as PDFs; these tests do not establish a direct-image upload feature. The corpus has 137 distinct file hashes and is a development corpus, not 139 independent held-out source families.

The completed OCR-enabled baseline at `821086d` generated and independently validated 90/139 files (64.75%); 43 failed or were refused and six timed out. This is whole-file generation success, not whole-corpus accuracy or production acceptance. The follow-up source is frozen for a separate complete rerun.

Follow-up code verification: 630 unit/integration tests across 75 files and 31 Python checks passed; TypeScript/build and lint of the changed JavaScript/TypeScript files passed. The cumulative browser run had 637 passed, four skipped and five failures. Two sitemap failures came from missing feature flags in the local SEO generation command; after correcting the invocation, all ten SEO browser checks passed. Three pre-existing WebKit navigation failures remain. Repository-wide lint also reports three unchanged Node-global errors in the existing Excel validation script. The real local mobile-width upload, conversion, download and delete flow passed and its downloaded DOCX contains actual two-column Word sections. The subsequent Python-only U2 class fix reran the Python and cumulative unit/integration suites; browser assets did not change.

Real Word testing uses isolated copies, verifies the intended active document before PDF export, inserts an edit marker, saves and reopens, and checks that table and Office Math counts survive. PDF export and visual inspection are recorded separately. Eight focused documents passed the Word operations; supported inline equations and the aligned two-column fixture were visually checked in actual Word. A complex historical-page probe expanded to three pages and a mixed chart/table probe expanded to two, so compatibility success must not be presented as layout-fidelity success.

Text reference comparison uses three upstream transcriptions, removing whitespace only and counting Levenshtein character errors. The previous frozen candidate reproduces 100%, 99.71% and 96.37% character agreement. The historical reference includes punctuation, line-end hyphens, reading-order and transcription artifacts. These measurements cover 3/139 files and do not establish whole-corpus accuracy. An experimental higher-resolution route worsened the historical reference score and was rolled back; its output is not final-candidate accuracy evidence.

An image-checked diagnostic of that historical comparison found 48 difference groups: 29 punctuation-form changes, 13 joined line-end hyphens, three reference artifacts, two moved side-caption groups and one letter-case change. These are diagnostic alignment groups, not the Levenshtein edit count. The original strict score remains unchanged; calling all of its 3.63% difference OCR misrecognition would be inaccurate.

Twelve explicitly mapped upstream table regression references add strict grid comparison. Text in a merged cell is attributed only to its top-left owner; repeated `python-docx` merged-cell proxies are not counted as recognition errors. Shape mismatches and failed conversions count as unmatched in this metric. Strict grid agreement, semantic merged-cell equivalence, full-document text accuracy and visual fidelity remain separate claims. All exact source mappings, downloaded references and per-file reports stay outside Git.

Linux GPU testing does not require a cloud server. A local Linux machine with an appropriate NVIDIA GPU can perform the target acceptance. This Apple Silicon host cannot establish CUDA compatibility, GPU isolation, device memory limits or target concurrency. The new OCR adapter remains explicitly local-only; the unchanged production image still runs v1.

## Completed whole-file benchmark and output corrections

The frozen `c47f619` candidate completed all 139 files: **94 generated and independently validated (67.63%)**, 44 failed/refused and one explicitly classified timeout. Some failed rows are whole-task cancellations at approximately 270 seconds; the single timeout count must not be interpreted as the total number of budget-related failures. The baseline remains 90/139 (64.75%). Five files recovered and one 20-page mixed document that previously took 250 seconds hit the 270-second limit in this run. All input hashes, successful output hashes and frozen converter source hashes were audited. No failed whole file was replaced with a successful page excerpt.

The three text references reproduce **100%, 99.71% and 96.37%** whitespace-normalized character agreement, covering only 3/139 files. Overall corpus accuracy remains **unmeasured**. Of twelve upstream table references, eleven now convert, but only five have identical complete grids; strict cell agreement is 605/2762. Shape mismatches and failed conversions remain unmatched. Conversion coverage improved without establishing general table reconstruction accuracy.

All 94 generated candidate documents were tested in actual Microsoft Word 16.115. Eighty-nine passed edit/save/reopen/PDF export and preservation checks. Five failed because Word merged independent adjacent tables. Among the 89 passing unedited exports, only 54 retained the source page count; matching page counts are not sufficient proof of fidelity. Visual review confirms narrow table columns can cause excessive wrapping and page expansion.

Two output corrections follow this frozen benchmark. Independent adjacent tables now have a minimal separating paragraph, while explicit cross-page continuations still reuse one table. The independent validator also accepts an image-containing body whose editable text resides in actually referenced headers/footers; empty bodies, pure images without editable text and orphan margin parts remain rejected. These changes pass 634 unit/integration tests across 75 files, 32 Python checks, TypeScript and changed-file lint. Their targeted real-document rerun is separate evidence and does not silently rewrite the frozen 139-file rate.

All six affected whole documents passed the targeted rerun, independent validation and actual Word edit/save/reopen/export. This resolves the five observed table-merging compatibility failures and recovers one previously rejected illustrated document. Body and margin text, images, source-page markers, table counts and editable formulas survive Word saving. Complex-table pagination remains unresolved; these six results do not constitute a second full 139-file benchmark.

The fixed synthetic suite and combined fixture pass marker checks and independent output checks, with encrypted, malformed and over-limit refusals preserved. Fifteen supported synthetic/focused outputs pass actual Word operations and body/margin/image preservation checks. The scanned mathematics probe retains **23 editable Office Math objects** after Word editing; its roots, fractions, indices, summation and superscript footnotes were visually inspected. Display-formula regions and diagrams remain images. The two-column and merged-cell probes were also inspected in actual Word exports.

The user authorized an isolated AWS acceptance project with a US$20 hard limit, a US$15 test target and SSH restricted to the approved single client IP using a dedicated temporary key. A temporary CPU Linux verification machine has a two-hour automatic stop timer; a pinned browser verification image and dependency cache have been prepared. The requested eight GPU vCPUs are still awaiting AWS approval, so CUDA inference, isolation and concurrency are not yet verified. Only reviewed repository code and synthetic fixtures may be transferred; the 139-file local corpus remains local. Production has not been changed and general-release acceptance remains false.
