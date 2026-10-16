import { it, expect } from "vitest";
import { pageRange } from "../src/organize/range";
it("selects current positions in order without duplicates", () => {
  expect(pageRange("3-8, 12, 4，1", 20)).toEqual([0, 2, 3, 4, 5, 6, 7, 11]);
  expect(pageRange("1–200", 200)).toHaveLength(200);
});
it("rejects partial, reversed, fractional and out-of-range selection", () => {
  for (const value of [
    "",
    "0",
    "3-1",
    "1,",
    "1.5",
    "1e2",
    "201",
    "1-999999999999",
    "1,,2",
  ])
    expect(() => pageRange(value, 200)).toThrow();
});
