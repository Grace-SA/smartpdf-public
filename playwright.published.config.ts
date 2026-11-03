import { defineConfig } from "@playwright/test";
import base from "./playwright.github.config";

export default defineConfig({
  ...base,
  testMatch: "published-tools.spec.ts",
  workers: 1,
  outputDir: "test-results-published",
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/github-published-browser.json" }],
  ],
});
