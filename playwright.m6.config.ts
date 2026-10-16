import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  testMatch: "compress.spec.ts",
  timeout: 140000,
  expect: { timeout: 30000 },
  workers: 1,
  use: {
    baseURL: process.env.M6_BASE_URL || "http://127.0.0.1:4206",
    viewport: { width: 1280, height: 900 },
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { browserName: "chromium" } },
    { name: "webkit", use: { browserName: "webkit" } },
  ],
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/m6-browser-regression.json" }],
  ],
  outputDir: "test-results-m6",
  webServer: {
    command:
      "node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 4206 --strictPort",
    port: 4206,
    reuseExistingServer: false,
  },
});
