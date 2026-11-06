import { execFileSync } from "node:child_process";
import { expect, it } from "vitest";
import { entries } from "../src/word/preflight-core";
import { docxFixture } from "./docx-fixture";

it("allows a larger PPT package without raising Word or per-entry budgets", () => {
  const bytes = docxFixture(
    undefined,
    {
      "padding-a.bin": "a".repeat(16 * 1024 ** 2),
      "padding-b.bin": "b".repeat(16 * 1024 ** 2),
    },
    false,
  );
  expect(() => entries(bytes)).toThrow();
  expect(entries(bytes, 60 * 1024 ** 2)).toHaveLength(4);
  expect(() =>
    entries(new Uint8Array(60 * 1024 ** 2 + 1), 60 * 1024 ** 2),
  ).toThrow();
});

it("checks slide scope, relationships, active content, geometry and resource boundaries", () => {
  expect(() =>
    execFileSync(
      process.platform === "win32" ? "python" : "python3",
      ["-B", "server/ppt/test_preflight.py"],
      { encoding: "utf8" },
    ),
  ).not.toThrow();
});

it("checks static SVG references, active content and expansion budgets", () => {
  expect(() =>
    execFileSync(
      process.platform === "win32" ? "python" : "python3",
      ["-B", "server/ppt/test_svg.py"],
      { encoding: "utf8" },
    ),
  ).not.toThrow();
});
