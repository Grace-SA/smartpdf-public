import base from "./playwright.grouped-navigation.config";
import { defineConfig } from "@playwright/test";
export default defineConfig({
  ...base,
  testMatch: [
    "watermark.spec.ts",
    "watermark-shell.spec.ts",
    "home-performance.spec.ts",
    "grouped-navigation.spec.ts",
    "raster-return-paths.spec.ts",
    "processing-overlay.spec.ts",
    "seo.spec.ts",
  ],
  reporter: [
    ["list"],
    [
      "json",
      {
        outputFile:
          "releases/20261016-grouped-navigation/loading-fix-regression.json",
      },
    ],
  ],
  outputDir: "test-results-production-loading-fix",
});
