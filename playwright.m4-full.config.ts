import { defineConfig } from "@playwright/test";
import base from "./playwright.split.config";
export default defineConfig({
  ...base,
  testMatch: "**/m4-full-ui.spec.ts",
  projects: [{ name: "chrome", use: { channel: "chrome" } }],
  outputDir: "test-results-m4-full",
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/m4-full-ui-tests.json" }],
  ],
});
