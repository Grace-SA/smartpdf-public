# Smart PDF delivery rules

- Work on one feature at a time. Research product interaction and reusable technical options before implementation.
- The feature workflow in requirements section 15.5 is standing instruction. The user does not need to repeat it for each milestone. Research competitor tasks and open-source implementations, resolve technical risks, define and self-review the product/interaction baseline, then implement.
- Every new feature requires unit/integration tests, boundary cases, the entire cumulative regression suite and independent output verification. Preserve fixed regression sample identities and expected refusals. Recompare the finished interaction against competitors and fix required issues before delivering the first acceptance build.
- Start authorized local work autonomously. Ask only for genuine scope, privacy, paid-dependency or product tradeoffs that require the user's decision. Keep research findings and current milestone status in the repository documentation; local development never implies production authorization.
- Private user documents, photos, names, sample inventories and rendered pages must never be uploaded, committed, or attached to GitHub Actions. Local private-corpus validation remains local only.
- Only explicitly reviewed synthetic fixtures and publicly licensed product assets may enter Git. Run `node scripts/check-repository.mjs` before committing or pushing. Do not bypass the checks to add personal material.
- Develop locally, run unit/integration, edge-case and existing-feature regressions, then commit and push to GitHub. Use a feature branch for new work and review it before merging to main.
- Production must be built from a clean commit already present on GitHub, with the CI run for that commit successful and explicit user authorization to publish. Never publish uncommitted changes or pretend an old test run covers new code.
- Ordinary pushes run tests only; they must not automatically deploy production. Keep AWS login credentials on the developer machine. Do not add long-lived AWS keys to GitHub.
- Record the commit, tag, test evidence and artifact hash for each release. Keep old production assets and rollback data. Preserve the lossless Brotli delivery of existing fonts/WASM/resources when deploying.
- Browser emulation is not real-device acceptance. State skipped tests and known limits honestly.
