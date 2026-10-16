import base from "./playwright.review.config";
import { defineConfig } from "@playwright/test";
export default defineConfig({
  ...base,
  testMatch: [
    ...(base.testMatch as string[]),
    "raster-return-paths.spec.ts",
    "processing-overlay.spec.ts",
  ],
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/picker-fix-20261016-browser.json" }],
  ],
  outputDir: "test-results-picker-fix-20261016",
});
