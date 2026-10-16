// Inspect the Git index, never local private PDFs or credential stores.
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { execFileSync } from "node:child_process";

const git = (...args) =>
  execFileSync("git", args, { maxBuffer: 96 * 1024 * 1024 });
const files = git("ls-files", "-z")
  .toString("utf8")
  .split("\0")
  .filter(Boolean);
const inventory = JSON.parse(
  git("show", ":config/repository-assets.json").toString("utf8"),
);
const assets = new Map(inventory.assets.map((entry) => [entry.path, entry]));
const failures = [];
const blockedPath =
  /(?:^|\/)(?:\.aws|\.env(?:\..*)?|node_modules|releases|dist(?:-[^/]*)?|test-results[^/]*|private-samples|private-validation|\.git-tools|\.git-bootstrap-check)(?:\/|$)|\.(?:pem|key|p12|pfx|log|trace)$/i;
const binary = /\.(?:pdf|png|jpe?g|heic|icc|ttf|wasm|zip|gz)$/i;
const secrets = [
  /\b(?:AKIA|ASIA)[A-Z0-9]{16}\b/,
  /\bgh[pousr]_[A-Za-z0-9]{30,}\b/,
  /\bgithub_pat_[A-Za-z0-9_]{30,}\b/,
  /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/,
  /\baws_secret_access_key\s*[:=]\s*["']?[A-Za-z0-9/+]{30,}/i,
];
for (const file of files) {
  if (blockedPath.test(file)) {
    failures.push(`${file}: local-only path`);
    continue;
  }
  const content = git("show", `:${file}`);
  if (content.length >= 90 * 1024 * 1024)
    failures.push(`${file}: exceeds repository size limit`);
  if (binary.test(file) || content.includes(0)) {
    const approved = assets.get(file);
    const hash = crypto.createHash("sha256").update(content).digest("hex");
    if (
      !approved ||
      approved.sha256 !== hash ||
      approved.bytes !== content.length
    )
      failures.push(`${file}: binary missing reviewed provenance/hash`);
  } else {
    const text = content.toString("utf8");
    if (secrets.some((pattern) => pattern.test(text)))
      failures.push(`${file}: possible credential`);
    if (/\b[A-Z]:[\\/]+Users[\\/]/i.test(text))
      failures.push(`${file}: personal absolute path`);
  }
}
for (const [file] of assets)
  if (!files.includes(file))
    failures.push(`${file}: approved asset missing from index`);
if (failures.length) {
  console.error("Repository check blocked:\n" + failures.join("\n"));
  process.exit(1);
}
if (!fs.existsSync(path.join(".git", "HEAD")))
  throw new Error("Run from the Smart PDF repository root");
console.log(
  `Repository check passed: ${files.length} files; ${assets.size} reviewed binary assets; no detected credentials or personal paths.`,
);
