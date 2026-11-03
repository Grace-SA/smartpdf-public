// Create a reviewable, versioned build. This script never deploys to AWS.
/* global fetch, AbortSignal */
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { execFileSync } from "node:child_process";
import { prepareWordRuntime } from "./word-release-manifest.mjs";

const run = (exe, args, options = {}) =>
  execFileSync(exe, args, {
    encoding: "utf8",
    maxBuffer: 4 * 1024 * 1024,
    ...options,
  });
const git = (...args) => run("git", args).trim();
const pnpmCli = process.env.npm_execpath || process.env.SMARTPDF_PNPM_CLI;
if (!pnpmCli || !fs.existsSync(pnpmCli))
  throw new Error("Invoke this command with pnpm release:prepare.");
if (git("status", "--porcelain"))
  throw new Error(
    "Commit and push every source change before preparing a release.",
  );
if (
  git("remote", "get-url", "origin") !==
  "https://github.com/Grace-SA/smartpdf.git"
)
  throw new Error("Unexpected release repository.");
git("fetch", "origin", "main");
const commit = git("rev-parse", "HEAD");
if (commit !== git("rev-parse", "origin/main"))
  throw new Error("Release HEAD must match GitHub main exactly.");
const credentials = run("git", ["credential", "fill"], {
  input: "protocol=https\nhost=github.com\nusername=Grace-SA\n\n",
});
const password = credentials
  .split(/\r?\n/)
  .find((line) => line.startsWith("password="))
  ?.slice(9);
if (!password)
  throw new Error("Sign in to GitHub using Git Credential Manager first.");
const response = await fetch(
  `https://api.github.com/repos/Grace-SA/smartpdf/actions/runs?head_sha=${commit}&event=push&per_page=100`,
  {
    headers: {
      Authorization: `Bearer ${password}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    signal: AbortSignal.timeout(30000),
  },
);
if (!response.ok)
  throw new Error(`Could not verify GitHub checks (${response.status}).`);
const checks = (await response.json()).workflow_runs.filter(
  (item) => item.path === ".github/workflows/ci.yml",
);
if (
  !checks.length ||
  checks[0].head_sha !== commit ||
  checks[0].conclusion !== "success"
)
  throw new Error(
    "The latest GitHub checks for this exact commit must finish successfully.",
  );
const folder = path.resolve("releases", `git-${commit.slice(0, 12)}`);
if (fs.existsSync(folder))
  throw new Error(
    "Release folder already exists; inspect it rather than overwriting evidence.",
  );
fs.mkdirSync(folder, { recursive: true });
const archive = path.join(folder, "source.tar");
git("archive", "--format=tar", `--output=${archive}`, commit);
const source = path.join(folder, "source");
fs.mkdirSync(source);
run("tar", ["-xf", archive, "-C", source]);
run(process.execPath, [pnpmCli, "install", "--frozen-lockfile"], {
  cwd: source,
  stdio: "inherit",
});
run(process.execPath, [pnpmCli, "build"], {
  cwd: source,
  stdio: "inherit",
  env: { ...process.env, VITE_ENABLE_PROTECT: "false" },
});
const files = [];
const walk = (dir) => {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const file = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(file);
    else {
      const bytes = fs.readFileSync(file);
      files.push({
        path: path
          .relative(path.join(source, "dist"), file)
          .replaceAll("\\", "/"),
        bytes: bytes.length,
        sha256: crypto.createHash("sha256").update(bytes).digest("hex"),
      });
    }
  }
};
walk(path.join(source, "dist"));
const word = prepareWordRuntime(source, folder);
fs.writeFileSync(
  path.join(folder, "release.json"),
  JSON.stringify(
    {
      commit,
      branch: "main",
      checks: checks[0].html_url,
      builtAt: new Date().toISOString(),
      deployed: false,
      features: { word: true, unlock: true, protect: false },
      files,
      word,
    },
    null,
    2,
  ),
);
console.log(
  `Prepared GitHub commit ${commit}. Review the build and authorize deployment separately. Preserve the existing Brotli encoding and rollback objects when uploading.`,
);
