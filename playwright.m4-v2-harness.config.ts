import { defineConfig } from "@playwright/test";
import base from "./playwright.mobile-harness.config";
export default defineConfig({
  ...base,
  testMatch: "**/mobile-split-v2-harness.spec.ts",
  outputDir: "test-results-m4-v2-harness",
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/m4-v2-harness.json" }],
  ],
});
