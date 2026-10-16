import { defineConfig } from "@playwright/test";
import base from "./playwright.m10-full.config";

export default defineConfig({
  ...base,
  testMatch: [
    ...(base.testMatch as string[]),
    "grouped-navigation.spec.ts",
    "raster-return-paths.spec.ts",
    "processing-overlay.spec.ts",
  ],
  workers: 2,
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/github-browser.json" }],
  ],
  outputDir: "test-results-github",
  use: {
    ...base.use,
    baseURL: "http://127.0.0.1:4240",
    trace: "off",
    screenshot: "off",
    video: "off",
  },
  webServer: {
    command:
      "node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 4240 --strictPort",
    port: 4240,
    reuseExistingServer: false,
  },
});
