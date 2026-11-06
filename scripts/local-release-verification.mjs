/* global fetch, AbortSignal */
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { execFileSync } from "node:child_process";

export const requiredLocalChecks = [
  "install",
  "repository",
  "repository-guard",
  "fixtures-boundary",
  "fixtures-unlock",
  "typecheck",
  "lint",
  "unit",
  "pdf-numbers",
  "pdf-unlock",
  "pdf-protect",
  "build-review",
  "webkit-preflight",
  "webkit-stability",
  "browser-chromium",
  "browser-webkit",
  "build-publication",
  "publication-chromium",
  "publication-webkit",
];
const sha = (bytes) => crypto.createHash("sha256").update(bytes).digest("hex");
const requireProof = (condition, message) => {
  if (!condition) throw Error(`Local release verification: ${message}`);
};
const git = (root, ...args) =>
  execFileSync("git", args, {
    cwd: root,
    encoding: "utf8",
    maxBuffer: 4 * 1024 ** 2,
  }).trim();
function rows(report) {
  const result = [];
  function visit(suites) {
    for (const suite of suites || []) {
      for (const spec of suite.specs || [])
        for (const test of spec.tests || []) result.push({ spec, test });
      visit(suite.suites);
    }
  }
  visit(report.suites);
  return result;
}
function inventory(report) {
  return rows(report)
    .map(({ spec, test }) => `${spec.id}\0${test.projectName}`)
    .sort();
}
function fullBrowserCommand(command, browser, list) {
  return (
    typeof command === "string" &&
    command.includes("playwright.github.config.ts") &&
    new RegExp(`--project(?:=|\\s+)${browser}(?:\\s|$)`).test(command) &&
    /(?:^|\s)--list(?:\s|$)/.test(command) === list &&
    !/--(?:grep|repeat-each|last-failed|only-changed|shard)|\.spec\.[jt]s/.test(
      command,
    )
  );
}
export function verifyLocalRelease({ repository, commit, evidence }) {
  requireProof(/^[a-f0-9]{40}$/.test(commit), "invalid release commit");
  const file = path.resolve(evidence),
    base = fs.realpathSync(path.dirname(file));
  const raw = fs.readFileSync(file),
    manifest = JSON.parse(raw);
  const tree = git(repository, "rev-parse", `${commit}^{tree}`);
  requireProof(
    manifest.schema === 1 && manifest.mode === "local-equivalent",
    "unsupported evidence schema",
  );
  requireProof(
    /^[a-f0-9]{40}$/.test(manifest.sourceCommit),
    "invalid tested commit",
  );
  requireProof(
    manifest.sourceTree === tree &&
      git(repository, "rev-parse", `${manifest.sourceCommit}^{tree}`) === tree,
    "tested source tree differs from release",
  );
  git(repository, "merge-base", "--is-ancestor", manifest.sourceCommit, commit);
  requireProof(
    manifest.workflowSha256 ===
      sha(
        execFileSync("git", ["show", `${commit}:.github/workflows/ci.yml`], {
          cwd: repository,
        }),
      ),
    "workflow differs from tested scope",
  );
  requireProof(
    manifest.lockfileSha256 ===
      sha(
        execFileSync("git", ["show", `${commit}:pnpm-lock.yaml`], {
          cwd: repository,
        }),
      ),
    "dependency lock differs",
  );
  requireProof(
    manifest.authorization?.kind === "explicit-user-local-equivalent" &&
      manifest.authorization.reason?.trim().length >= 20 &&
      Number.isFinite(Date.parse(manifest.authorization.authorizedAt)),
    "explicit user exception is required",
  );
  requireProof(
    manifest.privacy?.syntheticOnly === true &&
      manifest.privacy?.privateFilesIncluded === false,
    "private evidence is forbidden",
  );
  const runner = manifest.runner,
    version = /^v?(\d+)\.(\d+)\.(\d+)$/.exec(runner?.nodeVersion || "");
  const pkg = JSON.parse(
    execFileSync("git", ["show", `${commit}:package.json`], {
      cwd: repository,
      encoding: "utf8",
    }),
  );
  requireProof(
    runner?.platform === "linux" &&
      runner.role === "browser" &&
      /^sha256:[a-f0-9]{64}$/.test(runner.imageId || "") &&
      runner.source === "git-archive",
    "a pinned Linux browser runner and clean archive are required",
  );
  requireProof(
    version &&
      (+version[1] > 24 || (+version[1] === 24 && +version[2] >= 15)) &&
      runner.pnpmVersion === pkg.packageManager.split("@").at(-1) &&
      /^\d+\.\d+\.\d+$/.test(runner.playwrightVersion || ""),
    "runner versions do not match the release toolchain",
  );
  const refs = new Map();
  function read(ref) {
    requireProof(
      ref &&
        typeof ref.path === "string" &&
        /^[\w./-]+\.(json|log|txt)$/.test(ref.path) &&
        !path.isAbsolute(ref.path) &&
        !ref.path.split("/").includes(".."),
      "invalid evidence path",
    );
    const resolved = fs.realpathSync(path.resolve(base, ref.path));
    requireProof(
      resolved.startsWith(base + path.sep) && fs.lstatSync(resolved).isFile(),
      "evidence escapes its directory",
    );
    const bytes = fs.readFileSync(resolved);
    requireProof(
      bytes.length > 0 &&
        bytes.length <= 64 * 1024 ** 2 &&
        sha(bytes) === ref.sha256,
      "evidence bytes changed",
    );
    requireProof(
      !refs.has(ref.path) || refs.get(ref.path).sha256 === ref.sha256,
      "conflicting evidence reference",
    );
    refs.set(ref.path, {
      path: ref.path,
      sha256: ref.sha256,
      source: resolved,
    });
    return bytes;
  }
  requireProof(
    Array.isArray(manifest.checks) &&
      manifest.checks.length === requiredLocalChecks.length &&
      new Set(manifest.checks.map((c) => c.id)).size ===
        requiredLocalChecks.length,
    "missing or duplicate checks",
  );
  const completed = [],
    summaries = [];
  for (const id of requiredLocalChecks) {
    const check = manifest.checks.find((c) => c.id === id);
    requireProof(
      check &&
        ["win32", "linux"].includes(check.platform) &&
        check.sourceTree === tree &&
        check.exitCode === 0 &&
        typeof check.command === "string" &&
        check.command.length > 5,
      `failed or missing ${id}`,
    );
    const start = Date.parse(check.startedAt),
      end = Date.parse(check.completedAt);
    requireProof(
      Number.isFinite(start) && Number.isFinite(end) && end >= start,
      `invalid ${id} timestamps`,
    );
    completed.push(end);
    read(check.log);
    if (id === "build-review" || id === "build-publication")
      requireProof(
        check.environment?.VITE_ENABLE_EXCEL === "true" &&
          check.environment?.VITE_ENABLE_PROTECT ===
            (id === "build-review" ? "true" : "false"),
        `incorrect ${id} feature scope`,
      );
    if (id === "unit") {
      requireProof(
        /vitest|pnpm\s+test/.test(check.command) &&
          !/\.test\.[jt]s|--(?:grep|testNamePattern|changed|last-failed|shard)/.test(
            check.command,
          ),
        "unit command selected a subset",
      );
      const report = JSON.parse(read(check.report));
      const assertions = (report.testResults || []).flatMap(
        (r) => r.assertionResults || [],
      );
      requireProof(
        report.success === true &&
          report.numFailedTests === 0 &&
          report.numFailedTestSuites === 0 &&
          report.numPassedTests >= 613 &&
          assertions.length === report.numTotalTests &&
          assertions.every((a) =>
            ["passed", "pending", "skipped", "todo"].includes(a.status),
          ),
        "unit report is incomplete or failed",
      );
      summaries.push({
        id,
        passed: report.numPassedTests,
        skipped: report.numPendingTests || 0,
      });
    }
    if (
      id.startsWith("browser-") ||
      id.startsWith("publication-") ||
      id.startsWith("webkit-")
    ) {
      const report = JSON.parse(read(check.report)),
        tests = rows(report),
        browser = id.endsWith("chromium") ? "chromium" : "webkit";
      const minimum = id.startsWith("browser-")
        ? 314
        : id === "webkit-preflight"
          ? 20
          : id === "webkit-stability"
            ? 6
            : 1;
      requireProof(
        check.platform === "linux" &&
          report.config?.version === runner.playwrightVersion &&
          !report.errors?.length &&
          report.stats?.unexpected === 0 &&
          tests.length >= minimum &&
          tests.some(({ test }) => test.status !== "skipped") &&
          tests.every(
            ({ test }) =>
              test.projectName === browser &&
              ["expected", "flaky", "skipped"].includes(test.status) &&
              (test.status === "skipped" ||
                test.results?.at(-1)?.status === test.expectedStatus),
          ),
        `${id} browser report is incomplete or failed`,
      );
      if (id.startsWith("browser-")) {
        requireProof(
          fullBrowserCommand(check.command, browser, false) &&
            fullBrowserCommand(check.inventory?.command, browser, true),
          `${id} commands selected a subset`,
        );
        const listed = JSON.parse(read(check.inventory));
        requireProof(
          listed.config?.version === runner.playwrightVersion &&
            inventory(listed).length >= 314 &&
            JSON.stringify(inventory(listed)) ===
              JSON.stringify(inventory(report)),
          `${id} differs from its complete test inventory`,
        );
      }
      summaries.push({
        id,
        passed: report.stats.expected,
        skipped: report.stats.skipped,
        flaky: report.stats.flaky,
      });
    }
  }
  requireProof(
    Date.parse(manifest.createdAt) >= Math.max(...completed),
    "evidence was sealed before checks completed",
  );
  return {
    mode: "local-equivalent",
    releaseCommit: commit,
    testedCommit: manifest.sourceCommit,
    sourceTree: tree,
    manifestSha256: sha(raw),
    authorization: manifest.authorization,
    runner,
    summaries,
    manifest: file,
    files: [...refs.values()],
  };
}

export function copyLocalReleaseProof(proof, folder) {
  const directory = path.join(folder, "verification");
  fs.mkdirSync(directory);
  fs.copyFileSync(
    proof.manifest,
    path.join(directory, "local-verification.json"),
  );
  for (const ref of proof.files) {
    const target = path.join(directory, ref.path);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.copyFileSync(ref.source, target);
  }
  const record = Object.fromEntries(
    Object.entries(proof).filter(
      ([key]) => !["manifest", "files"].includes(key),
    ),
  );
  return { ...record, path: "verification/local-verification.json" };
}

export async function verifyGitHubRelease(repository, commit) {
  requireProof(/^[a-f0-9]{40}$/.test(commit), "invalid GitHub release commit");
  const credentials = execFileSync("git", ["credential", "fill"], {
    cwd: repository,
    input: "protocol=https\nhost=github.com\nusername=Grace-SA\n\n",
    encoding: "utf8",
  });
  const password = credentials
    .split(/\r?\n/)
    .find((line) => line.startsWith("password="))
    ?.slice(9);
  if (!password)
    throw Error("Sign in to GitHub using Git Credential Manager first.");
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
    throw Error(`Could not verify GitHub checks (${response.status}).`);
  const checks = (await response.json()).workflow_runs.filter(
    (item) => item.path === ".github/workflows/ci.yml",
  );
  if (
    !checks.length ||
    checks[0].head_sha !== commit ||
    checks[0].conclusion !== "success"
  )
    throw Error(
      "The latest GitHub checks for this exact commit must finish successfully.",
    );
  return {
    mode: "github-ci",
    releaseCommit: commit,
    checks: checks[0].html_url,
  };
}
