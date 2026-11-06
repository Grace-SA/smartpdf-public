// Create a reviewable, versioned build. This script never deploys to AWS.
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { execFileSync } from "node:child_process";
import { prepareOfficeRuntime } from "./office-release-manifest.mjs";
import {
  verifyLocalRelease,
  copyLocalReleaseProof,
  verifyGitHubRelease,
} from "./local-release-verification.mjs";

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
const flags = process.argv.slice(2);
if (
  flags.length > 1 ||
  flags.some((flag) => !flag.startsWith("--local-verification="))
)
  throw new Error(
    "Use only the explicit --local-verification=<manifest> override.",
  );
const evidence = flags[0]?.slice("--local-verification=".length);
if (flags.length && !evidence)
  throw new Error("A local verification manifest is required.");
const localProof = evidence
  ? verifyLocalRelease({ repository: process.cwd(), commit, evidence })
  : undefined;
const github = localProof
  ? undefined
  : await verifyGitHubRelease(process.cwd(), commit);
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
const office = prepareOfficeRuntime(source, folder);
const verification = localProof
  ? copyLocalReleaseProof(localProof, folder)
  : github;
const word = office.word;
fs.writeFileSync(
  path.join(folder, "release.json"),
  JSON.stringify(
    {
      commit,
      branch: "main",
      checks: localProof ? verification.path : github.checks,
      verification,
      builtAt: new Date().toISOString(),
      deployed: false,
      features: {
        word: true,
        ppt: true,
        excel: process.env.VITE_ENABLE_EXCEL === "true",
        unlock: true,
        protect: false,
      },
      files,
      word,
      office,
    },
    null,
    2,
  ),
);
console.log(
  `Prepared GitHub commit ${commit}. Review the build and authorize deployment separately. Preserve the existing Brotli encoding and rollback objects when uploading.`,
);
