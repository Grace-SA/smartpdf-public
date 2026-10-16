import { test, expect } from "vitest";
import { supportsName } from "../src/sign/assets";
import { inspectSign } from "../src/sign/generate";
import { makeFixture } from "./fixtures";
test("bundled font coverage never silently substitutes missing glyphs", () => {
  for (const style of ["MaShanZheng", "Kalam", "Caveat"])
    expect(supportsName(style, "Alex Chen")).toBe(true);
  expect(supportsName("MaShanZheng", "王小明 Alex")).toBe(true);
  expect(supportsName("Kalam", "王小明")).toBe(false);
  expect(supportsName("Caveat", "😀")).toBe(false);
  expect(supportsName("unknown", "Alex")).toBe(false);
  expect(supportsName("Caveat", "   ")).toBe(false);
  expect(supportsName("Caveat", "A".repeat(120))).toBe(true);
  expect(supportsName("Caveat", "A".repeat(121))).toBe(false);
});
test("certificate signatures and genuine zero-page documents are refused before editing", async () => {
  for (const kind of ["signature", "zero-pages"] as const)
    await expect(inspectSign(await makeFixture(kind))).rejects.toThrow();
});
