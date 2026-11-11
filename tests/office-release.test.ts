import { afterEach, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { execFileSync } from "node:child_process";
import {
  officeRuntimePaths,
  prepareOfficeRuntime,
} from "../scripts/office-release-manifest.mjs";
import { wordRuntimePaths } from "../scripts/word-release-manifest.mjs";
const folders: string[] = [];
afterEach(() => {
  for (const p of folders.splice(0))
    fs.rmSync(p, { recursive: true, force: true });
});
function fixture() {
  const root = fs.mkdtempSync(
    path.join(os.tmpdir(), "office-release-reviewed-"),
  );
  folders.push(root);
  const source = path.join(root, "source"),
    output = path.join(root, "output");
  fs.mkdirSync(output);
  for (const file of [...wordRuntimePaths, ...officeRuntimePaths]) {
    fs.mkdirSync(path.dirname(path.join(source, file)), { recursive: true });
    fs.copyFileSync(file, path.join(source, file));
  }
  return { source, output };
}
it("packages both engines, scheduler, validation, frozen dependencies and service config", () => {
  const f = fixture();
  const m = prepareOfficeRuntime(f.source, f.output);
  const list = execFileSync(
    "tar",
    ["-tf", path.join(f.output, m.archive.path)],
    { encoding: "utf8" },
  );
  for (const file of [
    "server/office/admission.mjs",
    "server/ppt/layout.py",
    "server/ppt/svg_check.py",
    "server/pdfword/docx-check.mjs",
    "server/pdfword/worker.py",
    "server/word/standby.mjs",
    "pnpm-workspace.yaml",
    "patches/pdf-lib@1.17.1.patch",
    "infra/office/smartpdf-office.service",
  ])
    expect(list).toContain(file);
  expect(m.sharedAdmission).toBe(true);
  expect(m.pdfword.scope).toBe("simple-native-text-only");
  expect(m.pdfword.ocr).toBe(false);
  expect(m.archive.sha256).toMatch(/^[a-f0-9]{64}$/);
  expect(() => prepareOfficeRuntime(f.source, f.output)).toThrow(
    "already exists",
  );
});
it("refuses a missing adapter instead of making a frontend-only release", () => {
  const f = fixture();
  fs.unlinkSync(path.join(f.source, "server/ppt/layout.py"));
  expect(() => prepareOfficeRuntime(f.source, f.output)).toThrow("layout.py");
  expect(fs.readdirSync(f.output)).toEqual([]);
});
it("refuses changed PPT image or recipe provenance", () => {
  for (const kind of ["image", "recipe"]) {
    const f = fixture();
    if (kind === "recipe")
      fs.appendFileSync(
        path.join(f.source, "server/ppt/Dockerfile"),
        "\n# changed",
      );
    else {
      const p = path.join(f.source, "config/ppt-core.stirling-3.2.2.json"),
        j = JSON.parse(fs.readFileSync(p, "utf8"));
      j.imageId = "registry.example.invalid/unapproved:latest";
      fs.writeFileSync(p, JSON.stringify(j));
    }
    expect(() => prepareOfficeRuntime(f.source, f.output)).toThrow(
      "provenance",
    );
    expect(fs.readdirSync(f.output)).toEqual([]);
  }
});
