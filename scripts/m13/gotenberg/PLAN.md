# Gotenberg native-engine PoC — frozen plan

2026-10-28. User authorized this PoC, before formal product development.
Use only synthetic sources. No production API, public upload or private documents.

Keep the existing six DOCX bytes and SHA256 identities unchanged. Add ten sources
covering Chinese punctuation, bold/size changes, merged and nested tables, long
repeating tables, controlled row breaks, explicit pagination, mixed section
orientation and separate section headers. Freeze the new manifest before running.
Two corrupt/empty inputs are rejection checks, outside the positive denominator.

Compare base image fonts with the same image plus the repository's licensed Noto
Sans SC. Pin the image digest; record actual Gotenberg/LibreOffice/font versions,
font matching, input/output hashes, HTTP status and elapsed time. The two font
variants must receive exactly the same source bytes. Do not treat default font
fallback as a failure if glyphs remain correct; record the actual font and layout.

Required checks:

- all unique body markers exactly once; Chinese phrases retained;
- explicit page counts and section orientation match declared expectations;
- automatic pagination spans multiple normal-size pages, without clipping;
- repeated table headers, merged/nested cell content and long rows remain visible;
- PDF glyph bounds within page boxes; no missing glyph squares, overlaps or
  text/image clipping during page-by-page visual inspection;
- explicit font actually available/matched, with actual PDF fonts recorded;
- original inputs unchanged; outputs independently parsed and rendered;
- corrupt/empty sources return a non-success and no accepted PDF;
- deterministic repeated runs retain text/page geometry (PDF metadata may vary).

Structural pass is not Word fidelity. Without a Microsoft Word reference PDF,
report source-declared geometry and visual inspection only. Any reference made by
the same LibreOffice engine is not an independent Word-layout oracle.

Run one active request initially. Performance is elapsed conversion time in the
recorded machine/container environment, not cloud/mobile SLA or peak throughput.
Record cold startup separately from conversion. Do not silently tune/rewrite a
failed source or lower a gate after seeing output.

Runtime must be isolated from production and bind HTTP to loopback. Use non-root
image defaults, bounded memory/CPU, deny document-triggered external requests,
disable remote-download routes and Chromium routes. Containers are only research
services; the PoC client is not a production security/upload gateway.

Initial environment discovery found no Docker/WSL and an expired AWS session.
The user then explicitly chose local Docker/WSL installation. WSL, Ubuntu and
Docker were installed and the native runs completed; see the dated PoC results.
Do not publish simulated or WASM output as native Gotenberg evidence.
