import { defineConfig } from "@playwright/test";
import base from "./playwright.usability.config";
export default defineConfig({
  ...base,
  webServer: undefined,
  testMatch: "**/mobile-organize-harness.spec.ts",
  projects: [
    { name: "chrome", use: { channel: "chrome" } },
    { name: "webkit", use: { browserName: "webkit" } },
  ],
  outputDir: "test-results-mobile-harness",
  reporter: [
    ["list"],
    [
      "json",
      { outputFile: "docs/evidence/mobile-harness-fix-2026-10-08.json" },
    ],
  ],
});
