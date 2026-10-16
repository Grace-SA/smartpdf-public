# Local development → GitHub → production

Repository: https://github.com/Grace-SA/smartpdf (private).

Git records the source history. GitHub holds the remote copy and runs checks. AWS serves the production build. GitHub is not an extra hosting environment, and a push does not deploy the website.

## Normal feature workflow

1. Start one `feature/...` or `fix/...` branch from current `main`.
2. Research, implement and test locally. Keep personal sample checks local; use synthetic fixtures for shared tests.
3. Review the diff, run `pnpm repo:check`, commit a meaningful change and push the branch.
4. Open a pull request. Wait for **Smart PDF checks** to pass, then review and merge to `main`.
5. Wait for the checks on the merged `main` commit to pass. Obtain the user's production authorization.
6. Run `pnpm release:prepare` from clean, up-to-date `main`. It verifies the remote commit and the exact commit's latest successful GitHub run, exports committed source into a new release folder, installs pinned dependencies and builds a separate artifact. It never uploads to AWS.
7. Verify that artifact, publish it using the existing versioned AWS process, preserve Brotli encoding on resources, run the production smoke checks, and record the Git commit, artifact hashes and rollback reference. Add and push an annotated `release-YYYYMMDD-N` tag only after successful deployment.

If checks fail or authentication expires, stop the dependent release step; do not bypass the gate. Ordinary commits and local previews can continue independently. The first import records the current source baseline; it does not retroactively prove that the old production build was created by GitHub.

## What stays local

- User PDFs/photos, decrypted files, screenshots of user documents, sample inventories and private-corpus scripts.
- Credentials, `.aws`, `.env`, private keys and account authentication caches.
- `node_modules`, generated builds, historic evidence, release archives, rollback Lambda backups and local debug logs.
- Synthetic 50/100 MiB boundaries; CI recreates them from `scripts/m5-fixtures.py`.

The default ignore rules limit top-level content and exclude sensitive history. The index scanner additionally rejects likely credentials, personal absolute paths, unapproved binaries and oversized blobs. Binary hashes and provenance are listed in `config/repository-assets.json`. This is a preventive check, not a guarantee that arbitrary future text is free of personal information: review every diff. Never add personal files even to this private repository.

Local commit and push hooks run the scanner; Git hooks are not installed automatically on a new clone. After cloning, run `git config core.hooksPath .githooks`. GitHub CI repeats the scanner independently.

## Authentication and deployment

Use GitHub's browser/device authorization for the local Git client. Credentials belong in the OS credential store, never repository files. The local commit identity is `Smart PDF <hi@smartpdf.com.au>`; it does not change the GitHub account's profile or primary email.

AWS continues to use the existing temporary `smartworks-dev` login locally. No AWS secret is stored in GitHub and no automatic production deployment is enabled. A future automated deployment should use AWS OIDC and an explicitly reviewed least-privilege role.

The CI job uses only the account's available GitHub Actions allowance, cancels superseded runs and has a time limit. It does not enroll in a paid service. Available private-repository minutes and billing limits depend on the GitHub account; if execution is blocked by quota, the release gate stays closed until the required checks can run.
