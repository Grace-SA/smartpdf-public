# Preserve currency markers when dollar delimiters collide

## Actual content corruption

A generated native PDF containing `Total $5+$10=$15.` was converted successfully with no warning, but the DOCX contained an OMML expression `5+` followed by `10=$15.`. Its first two dollar signs were lost. The inline math parser paired two amount markers as formula delimiters. Independent review reproduced both the parser behavior and the actual exported package.

## Conservative change

When a single-dollar pair begins with a numeric amount and its ending dollar immediately introduces another numeric amount, the entire logical text unit preserves single-dollar expressions literally. Signs (including Unicode minus), leading decimal notation and thousands separators are retained, not normalized or numerically evaluated. This avoids a third/odd amount pairing with the beginning of a later single-dollar formula. Explicit `$$...$$` and `\(...\)` remain on their existing formula path.

This is NOT perfect currency classification. For example `$5+5$10 units` can mean a formula followed by a number; it is now conservatively retained as literal text. A genuine `$x_i$` expression sharing a collision paragraph is also retained literally. Its characters are preserved rather than guessed away. Ordinary mathematical paragraphs without a collision retain their existing behavior. Unknown explicit formula commands still follow the existing unsupported-formula path.

The decision is computed from each complete paragraph and passed to its original styled runs; it never combines different paragraphs, cells or pages. Runs remain in their original order with bold/italic/font-size metadata. No new cross-run formula reconstruction is attempted. Each table cell independently uses the same protection.

## Verification

- Six self-contained tests cover positive/negative/Unicode-minus/decimal/thousands amounts, repeated amounts, odd currency counts followed by single-dollar and explicit math, all-original-character preservation, dollar/sign/amount run splits, style preservation, independent subsequent math paragraphs, neighboring isolated dollar paragraphs, and table-cell scope.
- A real native PDF→DOCX test verifies exact editable strings with all dollar signs, no raster images and no accidental OMML.
- Existing currency testing now checks whole-string preservation and absence of formula/error segments rather than assuming a particular segmentation index. Unknown-math rejection assertions remain unchanged.
- Final full Python suite:196 tests in6.422s,193 passed and3 existing optional scan-quality tests skipped. The first run exposed the obsolete segmentation-index test assumption; after strengthening it to the content invariant, the final run passed.
- The partial-workspace repository checker still reports129 missing approved assets; it did not pass. Publish only these five exact text changes atop the complete existing remote tree, preserving every asset. No PDFs, DOCX files or private data are committed.

Verification concerns actual package text, run attributes and formula structure. No Office visual acceptance, real-container deployment, CI success, merger or production readiness is asserted.
