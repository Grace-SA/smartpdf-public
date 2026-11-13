# Native typography and continuation review, 2026-11-13

Base: `e4ed8493dcf826ec16c9f87d16b4445e6eaa7326`.

## Targeted public-document improvements

Using the same unchanged public W3C Word and OpenOffice samples documented in `pdfword-public-lists-review-2026-11-13.md`:

- Close, aligned heading lines of the same size/weight become one editable heading with an explicit line break. The OpenOffice title no longer has a separate heading paragraph's large inter-line gap.
- Native list continuations merge only when they align with the source item's hanging indent, remain close vertically, and match size/weight. Literal ordinals and punctuation remain unchanged. Separate list items, distant text and unindented text are not merged.
- Native runs preserve a bounded set of common font families instead of always choosing Arial. Source subset prefixes and common PostScript aliases map to approved family names. Unknown fonts retain Arial. No font files are embedded, downloaded or extracted, and no arbitrary PDF font identifier is emitted as an OOXML font family.
- Exported native list indentation follows bounded source geometry, so subsequent wrapped lines align with the item text rather than the bullet/number.

## Review and validation

Independent review identified nondeterministic majority-font ties and missing canonical aliases. Both fixed: first-glyph order resolves ties deterministically; canonical safe-family names are idempotent. Added negative and edit/reopen regressions.

- **107 Python tests passed, zero skipped**, including eight new typography test methods. Compileall passed.
- Both public outputs pass the independent Node DOCX package check and render in LibreOffice as **one page**.
- Source, DOCX and rendered PDF non-whitespace character multisets match for both samples. Reading-order and paragraph checks supplement this, but multiset equality alone is not an accuracy score.
- Rendered pages inspected: OpenOffice title spacing improves with serif family retained; both samples' list continuations now wrap with hanging indentation.
- Unmodified repository guard remains blocked by the same 129 reviewed assets unavailable in the partial checkout. No private data, PDFs, fonts, generated DOCX or rendered binaries committed.

## Limits

Font-family metadata is not a guarantee that the font is installed on the receiving computer: Word/LibreOffice may substitute it. Exact font metrics, line wrapping and page geometry are not certified. Mixed-family glyphs within one extracted word still use the deterministic majority family. Heading and list continuation inference remains conservative geometry-based reconstruction, not tagged-document semantics. The representative corpus, complete OCR models, Microsoft Word, full-checkout guard and successful exact-commit CI remain release gates. No merge/deployment or general-release claim.
