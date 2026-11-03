# Smart PDF

PDF tools at https://smartpdf.com.au, with local PDF processing and an explicitly started cloud Word conversion.

The recorded production baseline `release-20261028-1` includes eleven tools: Merge, Split, Organize, Images to PDF, Sign, Compress, Rotate, PDF to JPG/PNG, Watermark, Page Numbers and Unlock. Original documents stay on the user's device; results are new downloads. Signing is a visible mark, not a certificate-based digital signature. Compatibility and resource limits still apply.

M12 Unlock PDF passed user acceptance and was released. M11 Protect PDF is under source review and testing, with AES-256 opening protection, one-shot workers and independent validation; it is not deployed or accepted on a real device. See [the M11 report](docs/m11-report.md) and [M12 report](docs/m12-report.md). The research → design → implement → full regression → self-review workflow is standing instruction for every feature; it need not be requested again. Actual production state is recorded separately from source changes.

## Delivery

Develop and test locally → commit and push to this private GitHub repository → pass checks and review → authorize and publish a versioned build to AWS.

A push runs tests; it never deploys production automatically. See [the delivery workflow](docs/repository-workflow.md) and [requirements](docs/requirements-v1.1.md). Earlier releases predate this repository; the first import is a source baseline, not a claim about their build provenance.

## Local setup

Requires Node 24.15+ and pnpm 11.25.0.

Word to PDF additionally uses a self-hosted Stirling service. It uploads only after the user starts conversion; other tools continue processing locally. See [the Word service setup and validation](docs/m13-stirling-implementation.md) for its pinned image, Python/Docker requirements, same-origin proxy and local run instructions. Static frontend hosting alone does not provide Word conversion.

Production builds exclude the unaccepted Protect entry points and SEO page. Development keeps Protect available for review; CI builds with `VITE_ENABLE_PROTECT=true` to run its full regression, then rebuilds with the flag false to verify publication boundaries. The formal release preparer always sets it false. Word and the accepted Unlock tool remain published.

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
