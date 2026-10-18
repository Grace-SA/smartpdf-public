import { defineConfig } from "@playwright/test";
import base from "./playwright.github.config";
export default defineConfig({
  ...base,
  testMatch: ["numbers.spec.ts"],
  workers: 2,
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/m9-browser.json" }],
  ],
  outputDir: "test-results-m9",
});
