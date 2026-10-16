import base from "./playwright.m8-picker.config";
import { defineConfig } from "@playwright/test";
export default defineConfig({
  ...base,
  testMatch: [
    "responsive-navigation.spec.ts",
    "loading-navigation.spec.ts",
    "raster-picker.spec.ts",
    "ux-picker-dialog.spec.ts",
    "task-boundaries.spec.ts",
    "ux-leave.spec.ts",
    "seo.spec.ts",
  ],
  timeout: 160000,
  use: { ...base.use, baseURL: "http://127.0.0.1:4218", actionTimeout: 15000 },
  reporter: [
    ["list"],
    [
      "json",
      { outputFile: "docs/evidence/responsive-navigation-browser.json" },
    ],
  ],
  outputDir: "test-results-responsive-navigation",
});
