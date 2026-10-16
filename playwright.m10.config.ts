import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  testMatch: [
    "watermark.spec.ts",
    "watermark-shell.spec.ts",
    "responsive-navigation.spec.ts",
    "seo.spec.ts",
    "ux-preview-stability.spec.ts",
  ],
  timeout: 160000,
  expect: { timeout: 30000 },
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:4220",
    viewport: { width: 1280, height: 900 },
    hasTouch: true,
    actionTimeout: 20000,
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { browserName: "chromium" } },
    { name: "webkit", use: { browserName: "webkit" } },
  ],
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/m10-browser.json" }],
  ],
  outputDir: "test-results-m10",
  webServer: {
    command:
      "node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 4220 --strictPort",
    port: 4220,
    reuseExistingServer: false,
  },
});
