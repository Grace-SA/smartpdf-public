import { expect, it } from "vitest";
import { enabledTools, publicTools, toolFromPath } from "../src/routes";

it("publishes Word and Unlock while Protect remains in review", () => {
  const published = enabledTools();
  expect(published).toContain("word");
  expect(published).toContain("unlock");
  expect(published).not.toContain("protect");
  expect(toolFromPath("/protect-pdf/", published)).toBeNull();
  expect(published).not.toContain("excel");
  expect(toolFromPath("/excel-to-pdf/", published)).toBeNull();
  expect(enabledTools(true, true)).toEqual(publicTools);
});
