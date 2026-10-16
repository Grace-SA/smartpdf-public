// Inspect the Git index, never local private PDFs or credential stores.
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { execFileSync } from "node:child_process";

const git = (...args) =>
  execFileSync("git", args, { maxBuffer: 256 * 1024 * 1024 });
const entries = git("ls-files", "--stage", "-z")
  .toString("utf8")
  .split("\0")
  .filter(Boolean)
  .map((entry) => {
    const match = entry.match(/^\d+ ([0-9a-f]+) (\d+)\t([\s\S]+)$/);
    if (!match || match[2] !== "0")
      throw new Error(
        "Resolve unmerged Git entries before checking the repository.",
      );
    return { oid: match[1], file: match[3] };
  });
const files = entries.map((entry) => entry.file);
const ids = [...new Set(entries.map((entry) => entry.oid))];
const packed = execFileSync("git", ["cat-file", "--batch"], {
  input: ids.join("\n") + "\n",
  maxBuffer: 256 * 1024 * 1024,
});
const blobs = new Map();
let offset = 0;
for (const oid of ids) {
  const end = packed.indexOf(10, offset);
  const header = packed.subarray(offset, end).toString("ascii").split(" ");
  const size = Number(header[2]);
  if (
    end < 0 ||
    header[0] !== oid ||
    header[1] !== "blob" ||
    !Number.isSafeInteger(size) ||
    size < 0 ||
    end + 1 + size >= packed.length
  )
    throw new Error("Git object batch could not be verified.");
  blobs.set(oid, packed.subarray(end + 1, end + 1 + size));
  offset = end + 1 + size + 1;
}
const contentFor = (file) =>
  blobs.get(entries.find((entry) => entry.file === file)?.oid);
const inventory = JSON.parse(
  contentFor("config/repository-assets.json").toString("utf8"),
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
  const content = contentFor(file);
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
