import { defineConfig } from "@playwright/test";
import base from "./playwright.m8-full.config";
export default defineConfig({
  ...base,
  testMatch: ["raster.spec.ts"],
  grep: /eight-tool navigation|a ready tab converts offline|PNG Standard multi-page|reject large-50mb|reject 100mb/,
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/m8-recovery-browser.json" }],
  ],
  outputDir: "test-results-m8-recovery",
});
