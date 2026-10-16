import { defineConfig } from "@playwright/test";
import base from "./playwright.m4-improve-regression.config";
export default defineConfig({
  ...base,
  testMatch: "**/review-color.spec.ts",
  outputDir: "test-results-m4-improve-color",
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/m4-improve-color.json" }],
  ],
});
