import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  testMatch: [
    "sign.spec.ts",
    "task-boundaries.spec.ts",
    "task-read-consent.spec.ts",
    "ux-leave.spec.ts",
    "ux-preview-stability.spec.ts",
    "ux-picker-dialog.spec.ts",
  ],
  timeout: 60000,
  workers: 1,
  use: {
    baseURL: process.env.M5_BASE_URL || "http://127.0.0.1:4205",
    viewport: { width: 1280, height: 900 },
    hasTouch: true,
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { browserName: "chromium" } },
    { name: "webkit", use: { browserName: "webkit" } },
  ],
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/m5-browser-regression.json" }],
  ],
  outputDir: "test-results-m5",
});
