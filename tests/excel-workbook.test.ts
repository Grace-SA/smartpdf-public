import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { expect, it } from "vitest";
import { readSheets } from "../src/excel/workbook";

it("checks XLSX structure, selected sheets, print settings, formulas and active content", () => {
  const output = execFileSync(
    process.platform === "win32" ? "python" : "python3",
    ["-B", "server/excel/test_preflight.py"],
    { encoding: "utf8" },
  );
  expect(output).toBe("");
});
it("reads worksheet metadata locally without treating hidden sheets as visible", () => {
  const directory = mkdtempSync(path.join(tmpdir(), "excel-metadata-"));
  try {
    execFileSync(process.platform === "win32" ? "python" : "python3", [
      "-B",
      "scripts/excel/fixtures.py",
      directory,
    ]);
    const sheets = readSheets(
      new Uint8Array(readFileSync(path.join(directory, "selection.xlsx"))),
    );
    expect(sheets).toEqual([
      { index: 0, name: "Report", hidden: false },
      { index: 1, name: "Other", hidden: false },
      { index: 2, name: "Hidden", hidden: true },
    ]);
    const corrupt = readFileSync(
      path.join(directory, "selection.xlsx"),
    ).subarray(0, 100);
    expect(() => readSheets(corrupt)).toThrow();
    expect(() => readSheets(new Uint8Array(22))).toThrow();
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});
