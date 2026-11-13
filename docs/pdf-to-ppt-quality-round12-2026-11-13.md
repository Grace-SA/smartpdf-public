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
- Source-pixel equality is verified for paint preservation. Real LibreOffice/PowerPoint output rendering, model inference, and the fixed 417-document corpus are not rerun in this cloud environment. Do not reuse their old scores as coverage of this patch.
- The full repository checker was actually run. It fails because the partial checkout lacks 129 existing approved binary assets. The asset policy is not changed or bypassed to add material; publication is a text-only tree update preserving the original blob IDs. This is not a full repository-check pass.
- Whole-site cumulative regression, Windows/WPS and real-device acceptance, production capacity, and release acceptance remain outstanding. Existing workflow configuration and production settings are unchanged. No merge or deployment is authorized by this work.
- GitHub Actions budget exhaustion has been reported by the owner; exact-head CI must still be checked after publication, and absence/failure must not be reported as success.
