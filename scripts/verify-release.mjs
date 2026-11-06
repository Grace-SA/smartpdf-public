import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { execFileSync } from "node:child_process";
import {
  verifyLocalRelease,
  verifyGitHubRelease,
} from "./local-release-verification.mjs";

const args = process.argv.slice(2);
if (args.length !== 2 || args[0] !== "--release")
  throw Error("Use --release <prepared folder>.");
const folder = path.resolve(args[1]),
  repository = process.cwd();
const release = JSON.parse(
  fs.readFileSync(path.join(folder, "release.json"), "utf8"),
);
if (release.branch !== "main" || !/^[a-f0-9]{40}$/.test(release.commit))
  throw Error("Expected a main release.");
const git = (...values) =>
  execFileSync("git", values, { cwd: repository, encoding: "utf8" }).trim();
if (
  git("remote", "get-url", "origin") !==
    "https://github.com/Grace-SA/smartpdf.git" ||
  git("ls-remote", "origin", "refs/heads/main").split(/\s/)[0] !==
    release.commit
)
  throw Error("Release is not current GitHub main.");
let proof;
if (release.verification?.mode === "local-equivalent") {
  if (release.verification.path !== "verification/local-verification.json")
    throw Error("Invalid evidence location.");
  proof = verifyLocalRelease({
    repository,
    commit: release.commit,
    evidence: path.join(folder, release.verification.path),
  });
  if (
    proof.manifestSha256 !== release.verification.manifestSha256 ||
    proof.sourceTree !== release.verification.sourceTree ||
    proof.testedCommit !== release.verification.testedCommit
  )
    throw Error("Release evidence record changed.");
} else {
  if (release.verification && release.verification.mode !== "github-ci")
    throw Error("Unknown release verification mode.");
  proof = await verifyGitHubRelease(repository, release.commit);
}
for (const row of release.files) {
  if (path.isAbsolute(row.path) || row.path.split(/[\\/]/).includes(".."))
    throw Error("Invalid build path.");
  const bytes = fs.readFileSync(path.join(folder, "source/dist", row.path));
  if (
    bytes.length !== row.bytes ||
    crypto.createHash("sha256").update(bytes).digest("hex") !== row.sha256
  )
    throw Error(`Build artifact changed: ${row.path}`);
}
console.log(
  JSON.stringify({
    passed: true,
    commit: release.commit,
    mode: proof.mode,
    testedCommit: proof.testedCommit,
    sourceTree: proof.sourceTree,
    files: release.files.length,
  }),
);
