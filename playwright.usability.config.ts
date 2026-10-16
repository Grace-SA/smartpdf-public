import { defineConfig } from "@playwright/test";
import base from "./playwright.review-retry.config";
const use = { ...base.use };
delete use.channel;
export default defineConfig({
  ...base,
  use,
  testMatch: [
    "**/usability.spec.ts",
    "**/review-color.spec.ts",
    "**/heic.spec.ts",
  ],
  projects: [
    { name: "chrome", use: { channel: "chrome" } },
    { name: "edge", use: { channel: "msedge" } },
    { name: "webkit", use: { browserName: "webkit" } },
  ],
  outputDir: "test-results-usability",
  reporter: [
    ["list"],
    [
      "json",
      { outputFile: "docs/evidence/color-usability-browser-2026-10-08.json" },
    ],
  ],
});
