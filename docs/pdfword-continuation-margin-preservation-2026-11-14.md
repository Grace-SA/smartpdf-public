# Preserve source-page margins across continued tables

## Reproduced loss

A generated two-page native PDF has an Inventory / Inventory (continued) heading and reporting-year footers2023 /2024. Each page contains20 numeric rows in a ruled table. Existing native parsing correctly identifies both margins and a continued table, but DOCX export merges the table and skips the entire second page's margins. The resulting package contains only2023 and Inventory;2024 and the continuation heading disappear. Independent review reproduced the actual PDF-to-DOCX path.

This is a content-preservation fix, not a new layout engine. A continuation may share an existing section only when source margin content, formatting and geometry match (identity/source metadata are excluded). Otherwise the exporter uses its existing independent-page section/table path. Both header and footer are explicitly disconnected there: an absent source margin means empty, not inherited text from the prior section. Column-flow continuous sections retain their existing behavior.

Continued-table appends must follow the immediately preceding page's trailing body table and its logical chain, then use the most recently emitted physical table. This prevents an A→B→B margin sequence from appending page3 back into page1's table after page2 created a new section. A nonadjacent stale reference does not authorize an append.

## Verification and limits

- All46 Python source/test blobs were fetched and matched against remote Word head8902b2e4aae962d4588abdc290021e50d86318fb before edits.
- Five new self-contained tests cover the real native PDF, all40 numeric values, exact per-section header/footer text, same/changed/new/removed margins, removed header, formatting changes, A→B→B and A→B→A, stale nonadjacent references and input-model immutability.
- Final complete Python suite:190 tests in6.424s,187 passed and3 existing scan-quality tests skipped because their optional model environment is absent. The initial run lacked the remote runtime config and had one import error; after fetching that same-head config, the final run above passed.
- Independent final review reran all five new tests successfully (0.507s) and found no blocker.
- Validation inspects the actual DOCX content and section/table relationships, not screenshots. No Office renderer or real-container deployment acceptance is claimed. Separating pages can change visual pagination; precise visual parity remains unverified.
- The repository checker was run against this partial indexed workspace and reports129 missing approved assets. It did not pass. Remote publication must preserve the full existing tree; only the exact three text deltas may be applied.
- Publication is only three text files (exporter, generated-fixture test and this note), built on the complete remote tree. No user/source PDFs, generated Word files or dependency binaries are included. No merge/deployment or CI success is implied.
