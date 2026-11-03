import { afterEach, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import crypto from "node:crypto";
import { execFileSync } from "node:child_process";
import {
  prepareWordRuntime,
  wordRuntimePaths,
} from "../scripts/word-release-manifest.mjs";

const folders: string[] = [];
afterEach(() => {
  for (const folder of folders.splice(0))
    fs.rmSync(folder, { recursive: true, force: true });
});
function fixture() {
  const root = fs.mkdtempSync(
    path.join(os.tmpdir(), "word-release-synthetic-"),
  );
  folders.push(root);
  const source = path.join(root, "source");
  const output = path.join(root, "release");
  fs.mkdirSync(output);
  for (const file of wordRuntimePaths) {
    fs.mkdirSync(path.dirname(path.join(source, file)), { recursive: true });
    fs.writeFileSync(path.join(source, file), "synthetic");
  }
  fs.writeFileSync(
    path.join(source, "server/word/runner.py"),
    `IMAGE = 'sha256:${"f".repeat(64)}'\n`,
  );
  fs.writeFileSync(
    path.join(source, "config/word-core.stirling-3.2.2.json"),
    JSON.stringify({
      flavor: "core",
      imageId: `sha256:${"f".repeat(64)}`,
      jar: { sha256: "a".repeat(64) },
      baseImage: `registry.example.invalid/base@sha256:${"b".repeat(64)}`,
      dockerfileSha256: crypto
        .createHash("sha256")
        .update("synthetic")
        .digest("hex"),
    }),
  );
  fs.writeFileSync(
    path.join(source, "config/word-fonts.stirling-3.2.2.json"),
    JSON.stringify({ profile: "synthetic", fonts: [{}] }),
  );
  return { source, output };
}
it("archives the workspace patch configuration with the backend and records hashes", () => {
  const { source, output } = fixture();
  const value = prepareWordRuntime(source, output);
  const names = execFileSync(
    "tar",
    ["-tf", path.join(output, value.archive.path)],
    { encoding: "utf8" },
  );
  expect(names).toContain("pnpm-workspace.yaml");
  expect(names).toContain("patches/pdf-lib@1.17.1.patch");
  expect(names).toContain("server/word/pdf-check.mjs");
  expect(names).toContain("server/word/core_build.py");
  expect(names).toContain("config/word-core.stirling-3.2.2.json");
  expect(value.archive.sha256).toMatch(/^[a-f0-9]{64}$/);
  expect(value.files).toHaveLength(wordRuntimePaths.length);
  expect(() => prepareWordRuntime(source, output)).toThrow("already exists");
});
it("refuses a mismatched core pin or modified build recipe", () => {
  const { source, output } = fixture();
  fs.writeFileSync(path.join(source, "infra/word/core.Dockerfile"), "changed");
  expect(() => prepareWordRuntime(source, output)).toThrow("core provenance");
  expect(fs.existsSync(path.join(output, "word-runtime.tar"))).toBe(false);
});
it("refuses the full upstream distribution even if its registry digest is fixed", () => {
  const { source, output } = fixture();
  fs.writeFileSync(
    path.join(source, "server/word/runner.py"),
    `IMAGE = 'registry.example.invalid/full@sha256:${"a".repeat(64)}'\n`,
  );
  expect(() => prepareWordRuntime(source, output)).toThrow(
    "fixed image digest",
  );
});
it("refuses an incomplete runtime rather than bypassing frozen dependency installation", () => {
  const { source, output } = fixture();
  fs.unlinkSync(path.join(source, "pnpm-workspace.yaml"));
  expect(() => prepareWordRuntime(source, output)).toThrow(
    "pnpm-workspace.yaml",
  );
  expect(fs.existsSync(path.join(output, "word-runtime.tar"))).toBe(false);
});
it("refuses an unpinned conversion engine", () => {
  const { source, output } = fixture();
  fs.writeFileSync(
    path.join(source, "server/word/runner.py"),
    "IMAGE = 'registry.example.invalid/engine:latest'\n",
  );
  expect(() => prepareWordRuntime(source, output)).toThrow(
    "fixed image digest",
  );
});
