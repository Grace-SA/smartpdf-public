import { afterEach, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import crypto from "node:crypto";
import { execFileSync } from "node:child_process";
import {
  requiredLocalChecks,
  verifyLocalRelease,
  copyLocalReleaseProof,
} from "../scripts/local-release-verification.mjs";
const roots: string[] = [];
const digest = (b: string | Buffer) =>
  crypto.createHash("sha256").update(b).digest("hex");
afterEach(() => {
  for (const root of roots.splice(0)) {
    if (
      !root.startsWith(path.resolve(os.tmpdir()) + path.sep) ||
      !path.basename(root).startsWith("smartpdf-release-proof-")
    )
      throw Error("Unsafe test cleanup");
    fs.rmSync(root, { recursive: true, force: true });
  }
});
function fixture() {
  const root = fs.mkdtempSync(
    path.join(os.tmpdir(), "smartpdf-release-proof-"),
  );
  roots.push(root);
  const repository = path.join(root, "repo"),
    evidence = path.join(root, "proof");
  fs.mkdirSync(path.join(repository, ".github/workflows"), { recursive: true });
  fs.mkdirSync(evidence);
  const git = (...args: string[]) =>
    execFileSync("git", args, { cwd: repository, encoding: "utf8" }).trim();
  git("init", "-q");
  git("config", "user.name", "Synthetic Release Test");
  git("config", "user.email", "release-tests@example.invalid");
  fs.writeFileSync(
    path.join(repository, ".github/workflows/ci.yml"),
    "synthetic workflow\n",
  );
  fs.writeFileSync(
    path.join(repository, "pnpm-lock.yaml"),
    "synthetic frozen lock\n",
  );
  fs.writeFileSync(
    path.join(repository, "package.json"),
    JSON.stringify({ packageManager: "pnpm@11.25.0" }),
  );
  git("add", ".");
  git("commit", "-qm", "synthetic source");
  const commit = git("rev-parse", "HEAD"),
    tree = git("rev-parse", "HEAD^{tree}");
  function file(name: string, value: unknown) {
    const bytes = typeof value === "string" ? value : JSON.stringify(value);
    fs.writeFileSync(path.join(evidence, name), bytes);
    return { path: name, sha256: digest(bytes) };
  }
  function browser(project: string, total: number, listing = false) {
    return {
      config: { version: "1.64.1" },
      errors: [],
      stats: { expected: total, unexpected: 0, skipped: 0, flaky: 0 },
      suites: [
        {
          specs: Array.from({ length: total }, (_, i) => ({
            id: "synthetic-" + i,
            tests: [
              listing
                ? { projectName: project }
                : {
                    projectName: project,
                    status: "expected",
                    expectedStatus: "passed",
                    results: [{ status: "passed" }],
                  },
            ],
          })),
        },
      ],
    };
  }
  const checks = requiredLocalChecks.map((id) => {
    const check: Record<string, unknown> = {
      id,
      sourceTree: tree,
      platform: "win32",
      command: "pnpm test --reporter=json",
      exitCode: 0,
      startedAt: "2026-11-06T00:00:00Z",
      completedAt: "2026-11-06T00:01:00Z",
      log: file(id + ".log", "synthetic successful check"),
    };
    if (id === "unit")
      check.report = file("unit.json", {
        success: true,
        numFailedTests: 0,
        numFailedTestSuites: 0,
        numPassedTests: 613,
        numPendingTests: 0,
        numTotalTests: 613,
        testResults: [
          {
            assertionResults: Array.from({ length: 613 }, () => ({
              status: "passed",
            })),
          },
        ],
      });
    if (id.startsWith("build-"))
      check.environment = {
        VITE_ENABLE_EXCEL: "true",
        VITE_ENABLE_PROTECT: id === "build-review" ? "true" : "false",
      };
    if (
      id.startsWith("browser-") ||
      id.startsWith("publication-") ||
      id.startsWith("webkit-")
    ) {
      const project = id.endsWith("chromium") ? "chromium" : "webkit",
        total = id.startsWith("browser-")
          ? 314
          : id === "webkit-preflight"
            ? 20
            : id === "webkit-stability"
              ? 6
              : 1;
      check.platform = "linux";
      check.command = `pnpm exec playwright test --config playwright.github.config.ts --project ${project}`;
      check.report = file(id + ".json", browser(project, total));
      if (id.startsWith("browser-"))
        check.inventory = {
          ...file(id + "-list.json", browser(project, total, true)),
          command: check.command + " --list --reporter=json",
        };
    }
    return check;
  });
  const manifest = {
    schema: 1,
    mode: "local-equivalent",
    sourceCommit: commit,
    sourceTree: tree,
    workflowSha256: digest("synthetic workflow\n"),
    lockfileSha256: digest("synthetic frozen lock\n"),
    createdAt: "2026-11-06T00:02:00Z",
    authorization: {
      kind: "explicit-user-local-equivalent",
      authorizedAt: "2026-11-06T00:00:00Z",
      reason: "Synthetic explicit local-equivalent release authorization",
    },
    privacy: { syntheticOnly: true, privateFilesIncluded: false },
    runner: {
      platform: "linux",
      role: "browser",
      source: "git-archive",
      imageId: "sha256:" + "a".repeat(64),
      nodeVersion: "v26.13.0",
      pnpmVersion: "11.25.0",
      playwrightVersion: "1.64.1",
    },
    checks,
  };
  const filename = path.join(evidence, "manifest.json");
  const save = () => fs.writeFileSync(filename, JSON.stringify(manifest));
  save();
  const verify = (release = commit) => {
    save();
    return verifyLocalRelease({
      repository,
      commit: release,
      evidence: filename,
    });
  };
  return {
    root,
    repository,
    evidence,
    git,
    commit,
    tree,
    manifest,
    checks,
    verify,
    file,
  };
}
it("accepts an identical-tree merge descendant, records the tested commit, and copies only referenced evidence", () => {
  const f = fixture();
  f.git("commit", "--allow-empty", "-qm", "synthetic merge identity");
  const merged = f.git("rev-parse", "HEAD");
  const proof = f.verify(merged);
  expect(proof.testedCommit).toBe(f.commit);
  expect(proof.releaseCommit).toBe(merged);
  fs.writeFileSync(
    path.join(f.evidence, "unreferenced-private-sentinel.txt"),
    "must never be copied",
  );
  const output = path.join(f.root, "release");
  fs.mkdirSync(output);
  copyLocalReleaseProof(proof, output);
  expect(
    fs.existsSync(
      path.join(output, "verification/unreferenced-private-sentinel.txt"),
    ),
  ).toBe(false);
});
it("refuses a source edit after testing even when the release is a descendant", () => {
  const f = fixture();
  fs.writeFileSync(path.join(f.repository, "changed.mjs"), "export default 1");
  f.git("add", ".");
  f.git("commit", "-qm", "synthetic later source");
  expect(() => f.verify(f.git("rev-parse", "HEAD"))).toThrow(/source tree/);
});
it("refuses changed evidence bytes and relative paths outside its proof directory", () => {
  const f = fixture();
  fs.appendFileSync(path.join(f.evidence, "unit.log"), "changed");
  expect(() => f.verify()).toThrow(/bytes changed/);
  const g = fixture();
  g.checks[0]!.log = { path: "../credential.txt", sha256: "a".repeat(64) };
  expect(() => g.verify()).toThrow(/invalid evidence path/);
});
it("refuses a missing scope, failed process, and unapproved local exception", () => {
  const f = fixture();
  f.checks.pop();
  expect(() => f.verify()).toThrow(/missing/);
  const g = fixture();
  g.checks[0]!.exitCode = 1;
  expect(() => g.verify()).toThrow(/failed/);
  const h = fixture();
  h.manifest.authorization.reason = "";
  expect(() => h.verify()).toThrow(/explicit user/);
});
it("rejects a failed assertion hidden behind successful unit aggregates", () => {
  const f = fixture();
  const check = f.checks.find((c) => c.id === "unit")!;
  const ref = check.report as { path: string };
  const report = JSON.parse(
    fs.readFileSync(path.join(f.evidence, ref.path), "utf8"),
  );
  report.testResults[0].assertionResults[0].status = "failed";
  check.report = f.file(ref.path, report);
  expect(() => f.verify()).toThrow(/unit report/);
});
it("rejects partial browser execution, filtered listings, and unexpected browser results", () => {
  const f = fixture();
  const c = f.checks.find((c) => c.id === "browser-webkit")!;
  const ref = c.report as { path: string };
  const r = JSON.parse(
    fs.readFileSync(path.join(f.evidence, ref.path), "utf8"),
  );
  r.suites[0].specs.pop();
  c.report = f.file(ref.path, r);
  expect(() => f.verify()).toThrow(/incomplete/);
  const g = fixture();
  g.checks.find((c) => c.id === "browser-chromium")!.command +=
    " --grep selected";
  expect(() => g.verify()).toThrow(/subset/);
  const h = fixture();
  const hc = h.checks.find((c) => c.id === "browser-webkit")!;
  const hr = hc.report as { path: string };
  const bad = JSON.parse(
    fs.readFileSync(path.join(h.evidence, hr.path), "utf8"),
  );
  bad.suites[0].specs[0].tests[0].results[0].status = "failed";
  hc.report = h.file(hr.path, bad);
  expect(() => h.verify()).toThrow(/incomplete or failed/);
});
it("requires review and publication builds to retain their different feature flags", () => {
  const f = fixture();
  f.checks.find((c) => c.id === "build-publication")!.environment = {
    VITE_ENABLE_EXCEL: "true",
    VITE_ENABLE_PROTECT: "true",
  };
  expect(() => f.verify()).toThrow(/feature scope/);
});
