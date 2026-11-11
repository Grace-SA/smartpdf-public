# PDF to Word implementation and acceptance

Status: Awaiting user acceptance. Production has not been changed. On 2026-11-11 the user deferred
publication and requested local acceptance first; production work must wait for
an explicit resumption.

## Approved product boundary

The development handoff selects a first release for simple native text PDFs.
Cloud conversion was explicitly approved; browser-only reconstruction was rejected
after feasibility research. The initial flow is one PDF, explicit **Upload and
convert**, visible stages, cancellation, **Download Word**, then deletion and a new
task. Selection performs a local signature check and does not upload document
bytes. The page identifies processing location and temporary retention. The result
is editable text, rather than a promise of identical fonts, wrapping or pagination.

Scans, existing OCR image pages, tables, columns, graphics, protected files,
annotations, interactive structures and ambiguous text are refused as whole files.
There is no engine selector. No OCR implementation is deployed in this milestone.
UnlimitedOCR2 remains the preferred research candidate for a later accepted OCR
worker; Mac research does not establish production-host readiness. OXR remains
research-only because its code and model licensing conditions differ.

Earlier fixed synthetic competitor uploads found better complex-document
reconstruction in iLovePDF and Smallpdf than the tested Stirling PDF/LibreOffice
import path. PDF24, pdf2docx and Stirling were retained as research comparisons,
not adopted as the primary reconstruction engine. Those measurements belong to
the earlier research session; this implementation does not claim competitor-level
complex-layout conversion or repeat uploads of local documents.

## Implementation

- A dedicated `pdfword` service reuses the Office session, upload, queue, expiry,
  cancellation and deletion lifecycle. Its cookie, task root and output MIME type
  are separate. Source bytes and expected-page metadata are removed before a
  successful result becomes downloadable.
- `parse_pdf` produces schema 1 document/page/block data. `export_word` writes
  actual Word paragraphs and source page-size sections. Raw text and PDFium
  coordinates remain separate from export. This is an initial model, not a
  general layout inference system.
- PDFium calls run serially in a disposable process. Each task has a non-root,
  read-only Docker container, no network, no host-directory mounts or ports,
  768 MiB memory, one CPU, 64 processes and a bounded tmpfs. Conversion has a
  90-second subprocess timeout and 120-second task watchdog. Input/output limits
  are 30 MiB, with 1–200 source pages and additional geometry/text/object budgets.
- Unsupported rendering modes, transparency, white text, clipping, rotated text,
  private-use/unmapped characters and right-to-left text are refused. The initial
  geometry policy is deliberately conservative and cannot identify every semantic
  layout from coordinates alone.
- Independent Node validation checks the DOCX ZIP directory, part bounds, CRCs,
  decompression budget, XML validity, main document content type and readable
  body text; it rejects external relationships and macro content types. It does
  not reuse the PDF importer or Word export library.
- The shared scheduler pauses Word's idle converter before another engine enters.
  Container cleanup failures mark the shared service unavailable. Late results
  cannot revive cancelled tasks.
- The image ID, base digest, recipe and dependency hashes are recorded in
  `config/pdfword-runtime.json`. Runtime licenses are retained and published in
  third-party notices. PyMuPDF is not a PDF-to-Word production dependency.

## Evidence recorded locally

| Check                                                                                | Result                                                                                                              |
| ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------- |
| Original 17 synthetic PDF identities                                                 | Retained; no fixtures replaced                                                                                      |
| Fixed synthetic support/refusal matrix                                               | 17/17 expected outcomes: 5 conversions, 12 refusals                                                                 |
| Independent pypdf layout extraction versus Word text                                 | 5/5 equal after whitespace normalization                                                                            |
| Local private corpus                                                                 | 30 checked locally: 2 converted, 28 refused; both converted texts independently matched                             |
| Python importer, editing, geometry, 200-page boundary, fault injection and isolation | 8 tests passed                                                                                                      |
| Service ownership, MIME, options, cancellation, output validation and deletion       | 5 tests passed                                                                                                      |
| Final full unit/integration regression                                               | 627 passed across 75 files                                                                                          |
| Final Linux WebKit cumulative browser regression                                     | 319 passed; 4 existing platform skips                                                                               |
| Final Chromium cumulative browser regression                                         | 323 passed with one worker                                                                                          |
| Independent existing-feature output verification                                     | Numbering: 374 pages; unlock: 33 documents/361 pages; protect: 21 documents/367 pages; all passed                   |
| LibreOffice render and visual checks                                                 | All 5 supported documents, 6 pages checked                                                                          |
| Real Microsoft Word checks                                                           | English and Chinese edits saved and independently reopened by a parser; two-page portrait/landscape layout observed |
| Real local HTTP/container conversion                                                 | Text PDF succeeded; scan refused; downloads and deletion checked                                                    |
| Navigation and SEO correction regression                                             | 17 Chromium tests passed                                                                                            |

The real browser-to-service workflow also passed against the offline local
worker: genuine Word download and independent text markers, a refused scan,
cancellation, a successful fresh conversion and deletion. The browser observed
no requests to external origins. The local task root was empty after cleanup.
The publication-scope Chromium and Linux WebKit checks each passed (one test per engine).

Resource measurements used fresh offline containers in an already running VM,
with the production 768 MiB / one-CPU limits. English, Chinese and a synthetic
200-page text PDF took 0.728–1.074 seconds in the worker (3.367–4.870 seconds
including orchestration), with cgroup peaks of 32.26–32.86 MiB. Independent OPC
checks passed for all three outputs; all 200 unique page markers were retained
in order. These simple fixtures do not establish a cold-start or production SLA.

Private names, source files, inventories, hashes, generated Word files and rendered
pages are excluded from Git, CI and cloud testing. Private outputs are isolated
outside the synchronized source workspace. Only aggregate results appear here.
Synthetic fixtures are generated from source in CI. Earlier fixed research PDFs
and all generated evidence remain local and ignored.

The independent text comparison initially used PDF content-stream order, which
placed a drawn footer ahead of body text. Comparing the independent parser's
geometric layout order confirmed the exported visual reading order for all five
supported fixtures; the initial diagnostic is retained rather than relabelled.

## Review and remaining release gates

This is author self-review, not an independent product acceptance. The completed
interaction was compared with the retained competitor screenshots and earlier
task logs; no new documents were uploaded to a third party. The selection-first
flow, explicit processing notice and prominent Word download are retained, with
complex-layout and OCR limitations stated before upload. Mobile-width
inspection found a selection-card grid mismatch inherited from the Office page;
the PDF-to-Word layout was corrected and a readable text-area assertion added.
The initial cumulative browser run exposed missing cloud-tool classification in
navigation tests and a missing generated SEO page. Both were corrected. The final Linux WebKit run passed 319 tests with four existing platform skips. Three oversized-input cases are covered by Chromium/core tests; one offline-worker case is skipped because native WebKit offline mode blocks local worker URLs. Chromium covers that case.

An isolated Linux browser attempt omitted the normal unlock-fixture generation
step; only the separate dense fixture existed. The resulting missing-file
failures were recorded, the setup was corrected to run the existing synthetic
generator, and the full browser pipeline was restarted without changing Unlock.

The first parallel browser/render attempt exhausted local Windows memory and
interrupted Linux containers. The subsequent single-worker Chromium run passed
all 323 tests; the earlier timeout record is retained. A full service regression
also exposed a genuine race between a cancellation-marker write and concurrent
directory deletion. The new delayed-write/concurrent-delete test fails against
the old committed implementation (two early deletion attempts) and passes after
the fix. Cleanup now waits for marker writes and joins in-flight deletion.

After the user closed an
unrelated protected-view dialog, a generated synthetic DOCX was opened in real
Microsoft Word. Original paragraphs were visually checked, a new editable
paragraph was added and saved, and independent DOCX parsing confirmed both the
original markers and the saved edit. Chinese editing and the two-page mixed-size
case were subsequently verified in Word too. These are representative Word
checks, not a claim about arbitrary complex PDFs.
Browser emulation is not real-phone acceptance.

GitHub currently reports that jobs cannot start because recent account payments
failed or the spending limit needs attention. The AWS login is also expired.
Neither condition permits using an earlier green run or a local override as a
successful exact-commit CI run.

After all acceptance gates pass: review and push the feature branch to the local
backup, GitHub and Codeup; verify all three object IDs; merge the reviewed PR;
replicate and verify the new main commit on all three destinations; obtain a
successful exact-main CI run; prepare the clean versioned release artifact;
install the fixed conversion image and runtime on the target host; validate with
public synthetic inputs; then enable the dedicated CDN/API route and publish the
frontend. Preserve previous static assets, Brotli transport and host rollback
configuration. Record artifact hashes and an annotated release tag only after
successful production smoke checks. Publication is currently deferred by the
user; neither earlier authorization nor local checks waive that hold or the
release gates.

## 2026-11-11 quality follow-up

The user's updated goal is broad common-file conversion quality, with code review,
fixes and GitHub submission only. The broader gate is defined in
[the quality standard](pdfword-quality-standard.md). This follow-up improves the
native-text milestone; it does **not** establish general-purpose readiness.
Earlier counts above belong to the earlier revision and were not rerun here.

Review and fixes:

- Inspect glyph advances inside each PDF text object. Large TJ positioning gaps,
  reversed/overlapping advances and an interleaved staggered-column case no longer
  silently become ordinary paragraphs. Preserve whole-file refusal, including
  when an unsupported page appears after supported pages.
- Reconstruct adjacent horizontal text runs, including split words, mixed sizes,
  Chinese runs and source spaces. Group compatible baselines before x-ordering.
  Follow the parser's inter-object separators rather than inventing spaces from
  a geometric threshold, which could change `123.45` to `123 .45`.
- Reconcile a uniquely named Docker container whenever creation was attempted,
  including when the client times out after a daemon-side creation. Report
  uncertain cleanup instead of treating the timeout as proof that nothing exists.
- Validate decoded OPC relationship attributes so character references and
  namespace prefixes cannot hide External relationships. Reject implicit absolute
  external targets as well.
- Strengthen the 200-page test with distinct ordered markers. Add an independent
  pypdf-versus-DOCX Chinese text check and edit/save/reopen regression.

Verified in the follow-up environment with the repository's pinned Python runtime
packages: 16 Python tests and 5 focused HTTP/service tests passed. Scoped JavaScript
format validation passed. Seven synthetic DOCX outputs passed independent OPC
validation and LibreOffice rendering, with exact text and one-page counts checked
by pypdf; Chinese and decimal-number page images were visually inspected. The
three encoded/prefixed/implicit external-target variants pass the old DOCX
validator and are rejected by the corrected validator. The new importer tests fail against the old worker:
four supported adjacent-run cases are wrongly refused, and five unsafe/partial
conversion assertions fail. Runner fault injection detects four failures against
the old implementation. Follow-up review found the small baseline-offset case; its fix is included. Numeric-spacing review found an invented-space case; its fix and
regression are included. Only original synthetic source generators are added.

Verification limits: this environment has no Docker engine or authenticated Git
clone. GitHub source reads produced a sparse materialization; large baseline
binary assets were unavailable through that route. The unchanged full repository
privacy/asset check therefore cannot pass here, and the cumulative frontend build,
browser suites and real-container pipeline were not rerun. Focused service tests
use the real HTTP service with synthetic worker output; runner tests fault-inject
Docker. These are not substitutes for the missing gates. No new Microsoft Word,
physical-phone or production-host acceptance is claimed. All unchanged remote
files and assets must retain their original blob IDs when this text-only update
is submitted. Production remains deferred.
