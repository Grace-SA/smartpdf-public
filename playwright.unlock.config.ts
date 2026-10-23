import { defineConfig } from "@playwright/test";
import base from "./playwright.github.config";
export default defineConfig({
  ...base,
  testMatch: ["unlock.spec.ts"],
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/m12-browser.json" }],
  ],
  outputDir: "test-results-unlock",
});
