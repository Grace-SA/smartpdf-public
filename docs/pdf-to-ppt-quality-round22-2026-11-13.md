# PDF-to-PPT round 22: licensed substitute-font trials

## Outcome

Three clearly licensed local font faces were evaluated on the dense second W-9 page, starting independently from the verified round-20 result with 726 editable source characters. This is **offline research**, not a production coverage increase. No font binary, public PDF, candidate deck or rendered page is committed. No production code or gate is changed in this round.

Most candidates failed strict multi-resolution comparison. A rebuilt Noto Sans candidate containing only two complete occurrences of `W-9` passes the separate round-21 geometry proof and unchanged four-resolution visual criteria, with six additional source positions. It still fails the default production guard's exact page-dimension rule. A narrow positive example is not authorization to replace that guard, and six positions do not establish broad document suitability.

## Candidate provenance and rights

Local font-internal declarations were checked against the corresponding preinstalled license documents; the exact bytes were hashed. Package-manager ownership/signature evidence was unavailable, so this is not represented as a signed-package provenance audit. These files were already present; no unknown font download or extraction from the proprietary PDF subsets was used.

| Face | Local version / size | SHA-256 | Embedding bits | License observed for these bytes |
| --- | --- | --- | --- | --- |
| Liberation Sans Regular | 2.1.5 / 410,820 bytes | `bade59d822652f76e6941aa87b40a87c13d1cc70db98ededb5011127efafd1d3` | 0 | OFL 1.1; Reserved Font Names must be respected for derivatives |
| Noto Sans Regular | 2.004 / 512,672 bytes | `89c3c497f618fdaa0b2d1e98fef93582f28c71debd2c4a8cdf41f190ced2909d` | 0 | OFL 1.1 |
| Open Sans Regular | 1.10 / 217,360 bytes | `e64e508b2aa2880f907e470c4550980ec4c0694d103a43f36150ac3f93189bee` | 8, preserved | Apache 2.0 for this older installed version, not the current upstream OFL release |

Upstream references: [Liberation license](https://github.com/liberationfonts/liberation-fonts/blob/main/LICENSE), [Noto license](https://github.com/notofonts/latin-greek-cyrillic/blob/main/OFL.txt), [current Open Sans upstream](https://github.com/googlefonts/opensans). Current upstream licensing must not be silently substituted for the license of a different installed version. Full notices and any applicable modification/name requirements would have to accompany a distributable integration.

The original full TTF bytes were embedded in temporary local trial decks without changing outlines, names or embedding permissions. The first general experiment correctly refused Open Sans at its fsType=0 assertion; its separate retry explicitly used the existing editable-embedding mode with fsType=8 unchanged. No restricted bit was cleared. All candidates cover the identifiable W-9 characters; the source's unmapped U+FFFE sentinel remains unrecognized, not guessed.

## Method

The input is the hash-checked W-9 selected-page artifact from `tools/public-native-manifest.json`, with the original page 2 evaluated at index 1 of the selected three-page PDF. Baseline and environment are the final round-20 artifact and the round-21 recorded Linux Office runtime.

Each face had two independent fits: median character height and source-word bounds. No additional vertical shift was introduced. The existing source-name eligibility, exact source ownership, complete word, local geometry/pixel, retained-pixel and original whole-page baseline gates were reused without weakening. Original source-order restoration was retained.

The experiments used temporary process-local candidate selection/embedding registration only. No face was added to the production font registry. For any preliminary addition, the full original TTF was embedded and verified byte-for-byte in EOT. Actual fontconfig selection and the exported PDF typefaces were checked against the intended files, not inferred from a textbox font label. The before/after-embedding PDFs are pixel-identical on all three selected W-9 pages.

Independent checks verify no prior source position or textbox XML is lost, unchanged slide XML remains identical, actual rendered text and ordered numeric tokens equal the editable textbox content, no source-extra numeric tokens appear, and new rendered characters actually use the tested font. The strict default guard is reported separately from the opt-in offline geometry/visual diagnostic.

## Six independent trials

| Font / fit | Preliminary source coverage | Added words / positions | Four-DPI per-word diagnostic |
| --- | --- | --- | --- |
| Liberation / median | 726 | 0 / 0 | No candidate reached final diagnostics |
| Liberation / bounds | 726 | 0 / 0 | No candidate reached final diagnostics |
| Noto / median | 747 | 10 / 21 | All ten refused |
| Noto / bounds | 735 | 3 / 9 | Two complete occurrences pass, page-heading occurrence refused |
| Open Sans / median | 739 | 3 / 13 | All three refused |
| Open Sans / bounds | 732 | 2 / 6 | One complete occurrence passes, page-heading occurrence refused |

Preliminary source positions are not accepted production coverage. Mixed candidate pages containing failed words are not declared safe.

## Rebuilt two-word positive control

The Noto bounds candidate was reconstructed from the unchanged baseline using only complete source ranges `[1151,1154)` and `[3352,3355)`, both literal `W-9`. It was refitted, rerendered, source-ordered and embedded again rather than deleting failed text from a previously accepted file or assuming per-region results compose.

Final experimental coverage is 732, six greater than 726. On the actual embedded result:

- Original source coverage and textbox XML are retained; the other two selected W-9 slides remain identical.
- Actual text, ordered numbers, intended typeface and full embedded font bytes are verified.
- Embedding introduces zero pixel difference on all three pages.
- The precise raw-decimal EMU/mm100 geometry proof passes, without image registration or resampling.
- Both final ROIs pass at 144/216/288/432 DPI, with no worsening of local MAE, foreground MAE or ink-edge error and exact previous-to-candidate pixels outside their union.
- The unchanged default production guard still returns `page_dimensions_differ`. The diagnostic continues to declare `production_acceptance: false`.

The Noto and Open Sans passing occurrence overlap, so their figures cannot be added together. These results do not justify hard-coding these source indices into production or claiming general text recovery.

## Verification and limits

This documentation-only round uses the reviewed round-21 code unchanged. Its existing cumulative result is 917 passed / 24 skipped; that is not presented as a new full-suite run. The six trials and rebuilt candidate above are new actual-render experiments with independent review. Repository checking and remote-tree preservation are performed for this documentation commit. No new wheel, merged release or deployment is claimed.

There is no substantive broad-coverage improvement yet. The main remaining barrier is font shape/spacing fidelity across dense ordinary text, not simply finding a font with a permissive license or matching total advance width. The narrow positive example also depends on an offline geometry contract that is not integrated into production. A future general implementation would need explicit reviewed font provenance/packaging, a deliberately scoped geometry-proof transaction, boundary and resource tests, final embedding parity, broader held-out documents and client acceptance. Until then, existing source-image fallback and production coverage remain unchanged.
