# PDF-to-PPT quality round 18 (2026-11-13)

## Scope and safety

Diagnostic improvements and a renderer-font consistency fix only. No service thresholds were relaxed, no automatic title refit was added, and no deployment or merge is authorized by this evidence. Raw public PDFs, fonts, generated presentations and rendered pages remain outside Git.

## Changes

- Add an independent 144/216/288/432 DPI diagnostic with frozen geometry-selected word pairs and integer-point ROIs. Candidate and image-only control are measured separately; no registration, resampling, baseline-error subtraction or acceptance verdict. Original 216 DPI diagnostics remain unchanged.
- Bound input snapshots, XML, pages, words, pixels, subprocess stderr/output and total deadline. Snapshot hashes identify the actual bytes used at every resolution. Exclusive output creation and inode-checked failure cleanup protect unrelated files. Record Poppler versions.
- Materialize CMU renderer fonts from the same hash-verified, alias-safe full TTF bytes used in embedded EOT. Remove raw CMU-directory fallback. Missing/tampered required files fail before Office invocation.
- Set accurate, style-specific OOXML pitch hints only for CMU Typewriter Text: regular/italic 49, bold/boldItalic 50, matching the approved faces’ differing pitch metadata. This corrected wrong-face selection in this Linux LibreOffice test without changing font bytes or thresholds.
- Preserve pinned source font timestamps in CMU/Noto payload generation so equal inputs remain equal across generation times.

## Findings and rejected approaches

The earlier eight-page public corpus is retained unchanged. Multi-resolution evidence separates sampling-sensitive measurements from persistent drift, but neither automatically excuses a failed original gate. In W-9 page 2, the common observed subset has non-monotonic foreground errors across resolutions. This is not evidence that every mismatch is harmless.

The paper title has a reproducible rightward drift in its final words across all four resolutions. Blanket character tracking and whole-title word refitting improved some words but worsened others, so neither was integrated. A temporary mixed-word proof preserved the first three words and corrected the last two: identical source text/numeric tokens/font payloads, other slide XML unchanged, and zero changed pixels outside edited-word ROIs at every resolution. This is a single-case offline experiment, not a general converter fix.

An initial experimental render omitted the configured CMU directory and changed unrelated author text. Independent whole-page comparison caught this; that evidence was rejected. Fresh original and experimental renders with identical complete font configuration confirmed the restricted change. The resulting production fix closes the silent CMU substitution path rather than accepting contaminated measurements.

The generic offline repair pilot initially rejected four PDFium-generated separator spaces in an otherwise complete source partition. A temporary, narrowly constrained separator check passed, but the replica then changed 353 pixels at 288 DPI and was rejected. No pilot code is committed or exposed in the service.

## Validation

Targeted font tests: 34 passed. Independent reviewer rerun: 33 passed, zero skips. New multi-resolution suite: 25 passed. All eight public pages completed the four-resolution diagnostic; common observed word counts were 0 (dummy), 90/55/49 (W-9), and 13/13/28/20 (paper). The zero-count page is an explicit abstention, not a pass. Poppler text extraction was 25.03.0 and rasterization 26.05.0. A wheel build succeeded (SHA-256 `3a39a277b9b055e7dde07a5671b9a2f5040879ec5260c71f33d9aabce93d8866`). Full cumulative regression: 731 passed, 24 skipped (Mac-specific font prerequisites), one upstream Starlette deprecation warning, 372.21 seconds. Fresh public conversion exposed a blocker despite these passing tests: paper page 1 lost 87 editable characters (five email addresses), while the other seven pages retained the previous metrics. Independent PDF font inspection found old CMU Typewriter Light selection and new Bold selection for text marked regular. Materialized-byte equality alone was insufficient. The blocker was traced to differing fixed-pitch declarations in the approved CMU faces. The exact-family, style-specific OOXML hint fixed the minimal real-render case. Ten new tests passed, including per-character Regular/Bold/Italic/BoldItalic identity both before and after embedding. Global weight changes, family renaming, and an all-fixed-pitch hint were tested and rejected. Final full regression/public results follow below. GitHub CI is not claimed; account quota is unavailable. Linux LibreOffice Development 26.8 is an experimental runtime, not Microsoft PowerPoint or production Office certification.

## Final verified result

- Final cumulative suite: **741 passed, 24 skipped**, one upstream deprecation warning, 355.39 seconds. The 24 skips require unavailable Mac-specific font prerequisites.
- All eight fresh public pages were independently re-extracted and checked. Seven retain exactly the previous coverage, numeric and pixel metrics. Paper page 1 now has **689/2461 editable characters**, versus 747 before this fix: this is a disclosed conservative coverage reduction, not a coverage improvement.
- The lost 58 source positions are exactly three email addresses. Independent comparison found their retained graphic regions pixel-identical to the original source-image baseline, with nonempty ink. The two still-editable email addresses occur once each and every visible glyph uses CMU Typewriter Regular. The final font set changes Typewriter Light to Regular, with no new Bold misselection. Old measurements used Light while the delivered EOT contained Regular; preserving that mismatch would not constitute a valid nonregression.
- Paper page 1 independently exact-matched words: 144/407 (previously 147/407); strict-box matches remain 0. No extra numeric tokens were added. Other seven pages remain unchanged, including their existing failures. Page 1 foreground MAE is 0.126863 versus 0.126320 previously. These figures are diagnostics, not an acceptance waiver.
- The final paper candidate was rerun through all four diagnostic resolutions. See the common-observed subset counts below; abstentions and strict-box failures remain explicit.
- Independent code review covered exact-family pitch scope, font provenance and diagnostic resource hardening; two documentation overstatements were corrected. The repository checker reports only 129 approved assets absent from this sparse checkout index, with zero other findings. Remote tree preservation is separately verified before publication.

Final paper common-observed word counts by selected page: [13, 13, 28, 20].

## Remaining release gates

Coverage is still partial on difficult pages; picture-preserved words are not editable. Strict Poppler box failures remain visible. Scans/OCR, uncommon fonts, equations, cross-client rendering, the unavailable private corpus, load/security/service integration and clean production CI remain separate gates. These results do not establish general production readiness or 100% recognition.
