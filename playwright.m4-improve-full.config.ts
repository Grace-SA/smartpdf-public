import { defineConfig } from "@playwright/test";
import base from "./playwright.m4-improve.config";
export default defineConfig({
  ...base,
  testMatch: "**/m4-full-ui.spec.ts",
  projects: [{ name: "chrome", use: { channel: "chrome" } }],
  outputDir: "test-results-m4-improve-full",
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/m4-improve-full-ui-tests.json" }],
  ],
});
