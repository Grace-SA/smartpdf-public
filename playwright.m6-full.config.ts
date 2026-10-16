import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  testMatch: [
    "compress.spec.ts",
    "sign.spec.ts",
    "task-boundaries.spec.ts",
    "task-read-consent.spec.ts",
    "ux-leave.spec.ts",
    "ux-preview-stability.spec.ts",
    "ux-picker-dialog.spec.ts",
  ],
  timeout: 140000,
  expect: { timeout: 30000 },
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:4207",
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
    ["json", { outputFile: "docs/evidence/m6-full-browser-regression.json" }],
  ],
  outputDir: "test-results-m6-full",
  webServer: {
    command:
      "node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 4207 --strictPort",
    port: 4207,
    reuseExistingServer: false,
  },
});
