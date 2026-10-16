import { defineConfig } from "@playwright/test";
import base from "./playwright.review-retry.config";
export default defineConfig({
  ...base,
  outputDir: "test-results-color-regression",
  reporter: [
    ["list"],
    [
      "json",
      {
        outputFile: "docs/evidence/color-usability-regression-2026-10-08.json",
      },
    ],
  ],
});
