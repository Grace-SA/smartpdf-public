// Synthetic index-only probes; no personal files are created or opened.
import { spawnSync } from "node:child_process";
const git = (args, input) => {
  const result = spawnSync("git", args, { encoding: "utf8", input });
  if (result.status !== 0) throw new Error("Git index probe operation failed.");
  return result.stdout.trim();
};
const probes = [
  { path: ".env.repository-check-probe", body: "synthetic repository check" },
  {
    path: "tests/repository-check-probe.txt",
    body: "example=" + "AK" + "IA" + "A".repeat(16),
  },
  {
    path: "tests/fixtures/repository-check-probe.pdf",
    body: "%PDF-1.7 synthetic unapproved test asset",
  },
];
for (const probe of probes) {
  if (git(["ls-files", "--", probe.path]))
    throw new Error("A probe path is already in use.");
  try {
    const oid = git(["hash-object", "-w", "--stdin"], probe.body);
    git([
      "update-index",
      "--add",
      "--cacheinfo",
      `100644,${oid},${probe.path}`,
    ]);
    const result = spawnSync(
      process.execPath,
      ["scripts/check-repository.mjs"],
      { encoding: "utf8" },
    );
    if (result.status !== 1 || !result.stderr.includes(probe.path))
      throw new Error("Repository guard did not reject a synthetic probe.");
  } finally {
    git(["update-index", "--force-remove", probe.path]);
  }
}
console.log(
  "All three synthetic repository guard probes were rejected correctly.",
);
