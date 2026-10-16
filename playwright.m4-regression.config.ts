import { defineConfig } from "@playwright/test";
import base from "./playwright.color-regression.config";
export default defineConfig({
  ...base,
  outputDir: "test-results-m4-regression",
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/m4-regression.json" }],
  ],
});
