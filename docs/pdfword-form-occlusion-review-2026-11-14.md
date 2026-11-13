# Nested Form paint-order review, 2026-11-14

Base: `3f191e29d377f5f866c52210927672717162b04e`.

## Reproduction and scope

Wrapping a narrow white amount-covering rectangle in a PDF Form XObject bypassed the previous top-level overlap guard: native output still exposed the complete underlying amount. This is reproducible using an original synthetic PDF, without private documents.

The overlap guard now follows descendant paint order and composes ancestor Form matrices to map bounds back into page coordinates. It compares nested text and graphics across Form/page boundaries. At the depth-eight traversal boundary, unseen Form descendants require OCR rather than being assumed safe. Existing object and overlap budgets remain enforced. A simple two-segment stroked line is also checked as a possible occluder; bounding boxes include stroke width.

Independent review found that the adjacent text crop/orientation guards still used local coordinates. These now use world-space bounds/effective matrices too. New tests verify translated-out-of-page text, rotated Form text, and text translated into the visible page. Review also requested actual differently transformed sibling Forms; those counterexamples were added.

## Verification

- Eleven new test methods cover nested/ancestor paint order, scale/translation multiplication order, disjoint graphics, true sibling transforms, transformed text safety, recursion limits, stroked-line cover/background/nonoverlap cases, and refusal without configured OCR.
- PDFium-rendered pixels for a nested transformed cover exactly match the equivalent page-space cover. This is independent of the overlap decision.
- Cumulative Python suite: **140 tests run, 137 passed, 3 skipped** because the OCR preprocessing environment is absent. Compileall passed.
- Unmodified repository guard: only 129 missing reviewed binary assets in the partial local index. No guard/configuration was weakened. Only code, synthetic fixture-generating tests and this aggregate report are committed, preserving all unrelated GitHub tree entries.

## Remaining limits

Complex stroked paths/curves, blend modes, clipping, soft masks and complete occlusion classification still require work. Bounding rectangles can conservatively request OCR when painted pixels do not obscure text. Recursion-limit routing may also reject otherwise convertible documents without OCR. Real OCR recognition, actual Word rendering, full-checkout/frontend/build/browser acceptance and exact-commit CI are not established by these tests. No production-readiness claim, merge or deployment.
