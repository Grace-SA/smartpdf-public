# PDF-to-PPT readiness review, round 12 (2026-11-13)

Base: `550079c17c544d1b372a31846061c855273f6c49`, experimental PDF-to-PPT branch. This round fixes reproducible correctness problems; it does not establish general production readiness.

## Fixes and review

1. **Fragmented numeric text.** The fixed source fixture `North 123.45` was emitted as `North 1 23.45` because the visible ink gap after the narrow glyph `1` exceeded the heuristic word-space threshold. Use PDFium's loose character advance boxes to distinguish an advance gap from a side bearing. Original ink boxes still determine layout and all source object provenance is retained. Both existing fragmented-object regressions failed before the change and pass after it.
2. **Text paint semantics.** Fill-only, fully opaque text is the supported editable paint operation. Transparent, stroked and clipping text objects previously became opaque filled text when removed from the source raster. They now remain untouched in that raster with explicit warnings. Eight synthetic paint-mode tests compare retained PDFium pixels exactly, assert no removals, and assert no editable replacement text; an opaque-fill control remains editable. This is an honest loss of editability for unsupported paint, not an increased coverage claim.
3. **Numeric acceptance.** The independent evaluator used a different numeric parser from conversion diagnostics. Leading decimals and separate numeric tokens could be lost while still passing the paragraph's small character-error tolerance. Both now use a shared ordered tokenizer, with meaningful separators retained. Review also found accounting parentheses and separated percentage marks were ignored; those are now retained. Order remains significant in independent evaluation, while diagnostic counters retain their existing meaning.

An independent read-only review reproduced the paint and decimal bugs and reran focused tests. Additional findings were fixed and covered by long-paragraph regressions; numeric corruption cannot be excused by a low aggregate CER in these cases.

## Verification and limits

- Original code against the first added regressions plus existing fragmented-object tests: 14 expected failures, 20 passes. No source samples or frozen expected outcomes were weakened.
- Final experimental backend suite: **473 passed, 67 skipped** (optional pinned fonts and real Office renderer unavailable). Python compileall also passed. Dependencies are installed from the unchanged requirements lock.
- All new fixtures are generated synthetic documents. No private corpus files or rendered pages are committed.
- Source-pixel equality is verified for paint preservation. Follow-up located the existing LibreOfficeDev 26.8 renderer and verified official pinned CMU, Noto Sans SC and Noto Serif SC font downloads. Real rendering results are recorded below. Model inference and the fixed 417-document corpus are not rerun in this cloud environment. Do not reuse their old scores as coverage of this patch.
- The full repository checker was actually run. It fails because the partial checkout lacks 129 existing approved binary assets. The asset policy is not changed or bypassed to add material; publication is a text-only tree update preserving the original blob IDs. This is not a full repository-check pass.
- Whole-site cumulative regression, Windows/WPS and real-device acceptance, production capacity, and release acceptance remain outstanding. Existing workflow configuration and production settings are unchanged. No merge or deployment is authorized by this work.
- GitHub Actions budget exhaustion has been reported by the owner; exact-head CI must still be checked after publication, and absence/failure must not be reported as success.


## Follow-up Linux rendering

After the initial submission, the cloud environment's existing LibreOfficeDev 26.8.0.0.alpha0 wrapper was located and exercised. The initial missing-renderer description is superseded by this follow-up, not silently treated as a previous test pass.

- Eight paint-mode outputs were opened and rendered independently by LibreOffice. Maximum full-page normalized pixel MAE was 0.000824; maximum foreground MAE was 0.047636. Fully transparent text remained visually blank (zero pixel error). These are appearance checks, not editable-text recovery.
- The renderer-enabled backend run without optional fonts had **487 passed, 51 skipped, 2 failed**. Both failures (`test_real_extension_keeps_prior_xml_and_can_roll_back`, `test_sparse_regional_recovery_matches_full_and_keeps_untouched_slides`) were rerun against the exact original implementation and fail there as well. Candidate regional text exceeds the existing pixel gate and correctly remains raster. No tolerance was loosened and no failure was skipped to produce a green result.
- Official CMU archive SHA-256 and Noto Serif SC font SHA-256 matched their existing manifests; 27 related font tests passed with 2 Noto Sans-dependent skips. The correct Noto Sans SC was subsequently recovered from the repository-recorded Google Fonts commit, with the existing SHA-256 matching. No downloaded font or private file is included in this commit.
- The exact code commit's GitHub workflow [43423025652](https://github.com/Grace-SA/smartpdf/actions/runs/43423025652) failed without job steps/logs. The owner reports exhausted Actions quota. Local verification is not a CI pass.
- Final broader run with all three verified font families and the real Office renderer: **514 passed, 24 skipped, 2 failed** in 229.27 seconds. The same two regional recovery failures remain; the 24 skips require installed macOS font acceptance. No additional failure appeared. This is materially broader evidence than the initial 473/67 run, but it is explicitly not an all-green production qualification.

Next readiness work is to improve source/Office glyph matching on Linux without relaxing the existing geometry or pixel gates, then rerun the fixed real/public corpus and cross-platform structure acceptance. Successful generation remains distinct from correct editable reconstruction.
