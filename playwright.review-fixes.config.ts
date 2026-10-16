import base from "./playwright.leave.config";
import { defineConfig } from "@playwright/test";
export default defineConfig({
  ...base,
  testMatch: [
    ...(base.testMatch as string[]),
    "ux-review-fixes.spec.ts",
    "ux-preview-stability.spec.ts",
  ],
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/ux9-regression.json" }],
  ],
});
