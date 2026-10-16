import base from "./playwright.picker-fix.config";
import { defineConfig } from "@playwright/test";
export default defineConfig({
  ...base,
  testMatch: [...(base.testMatch as string[]), "grouped-navigation.spec.ts"],
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/grouped-navigation-browser.json" }],
  ],
  outputDir: "test-results-grouped-navigation",
});
