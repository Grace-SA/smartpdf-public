import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  testMatch: [
    "home-performance.spec.ts",
    "loading-navigation.spec.ts",
    "rotate.spec.ts",
    "raster.spec.ts",
    "raster-picker.spec.ts",
    "responsive-navigation.spec.ts",
    "compress.spec.ts",
    "sign.spec.ts",
    "task-boundaries.spec.ts",
    "task-read-consent.spec.ts",
    "ux-leave.spec.ts",
    "ux-preview-stability.spec.ts",
    "ux-picker-dialog.spec.ts",
    "seo.spec.ts",
    "trust-ui.spec.ts",
  ],
  timeout: 140_000,
  expect: { timeout: 30_000 },
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:4216",
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
    ["json", { outputFile: "docs/evidence/m8-full-browser-regression.json" }],
  ],
  outputDir: "test-results-m8-full",
  webServer: {
    command:
      "node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 4216 --strictPort",
    port: 4216,
    reuseExistingServer: false,
  },
});
