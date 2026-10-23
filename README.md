# Smart PDF

Private, on-device PDF tools at https://smartpdf.com.au.

Nine tools are currently live: Merge, Split, Organize, Images to PDF, Sign, Compress, Rotate, PDF to JPG/PNG, and Watermark. Original documents stay on the user's device; results are new downloads. Signing is a visible mark, not a certificate-based digital signature. Compatibility and resource limits still apply.

M9 Add Page Numbers was accepted by the product owner on 23 October 2026 and is included in this source as the tenth tool. Final code/UX review found no release blockers; publication is authorized and remains gated on exact-main CI, a versioned artifact and post-deployment verification. Actual production state is recorded separately from the source. The research → design → implement → full regression → self-review workflow is standing instruction for every feature; it need not be requested again.

## Delivery

Develop and test locally → commit and push to this private GitHub repository → pass checks and review → authorize and publish a versioned build to AWS.

A push runs tests; it never deploys production automatically. See [the delivery workflow](docs/repository-workflow.md) and [requirements](docs/requirements-v1.1.md). Earlier releases predate this repository; the first import is a source baseline, not a claim about their build provenance.

## Local setup

Requires Node 24.15+ and pnpm 11.25.0.

```powershell
pnpm install --frozen-lockfile
git config core.hooksPath .githooks
pnpm build
pnpm dev
```

To recreate large synthetic boundary fixtures, install `scripts/requirements-test.txt` into `.local-python`, then run `python -B scripts/m5-fixtures.py`.

## Checks

```powershell
pnpm typecheck
pnpm test
pnpm build
pnpm exec playwright install chromium webkit
pnpm exec playwright test --config playwright.github.config.ts
```

Before committing, stage the reviewed changes and run `pnpm repo:check`. The same index checks also run in the local Git hooks and GitHub CI. CI regenerates the synthetic large-file boundaries before its tests. Desktop browser checks do not replace physical iPhone acceptance.

## Data boundaries

Never commit or upload personal PDFs, photographs, rendered document pages, private sample manifests, authentication credentials or release backups. Only reviewed synthetic test fixtures and licensed product resources are shared. The binary inventory is in `config/repository-assets.json`; generators and licenses document their provenance.

Runtime dependencies and their licenses are pinned by the lockfile and [license inventory](docs/dependency-licenses.json). Keep `patches/` and `pnpm-workspace.yaml`: the PDF parser resource guards are part of the product. Fonts, WebAssembly engines and notices are served from the same website.
