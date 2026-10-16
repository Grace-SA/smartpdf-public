import { defineConfig } from "@playwright/test";
import base from "./playwright.usability.config";
export default defineConfig({
  ...base,
  testMatch: ["**/split.spec.ts"],
  outputDir: "test-results-split",
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/m4-browser.json" }],
  ],
});
