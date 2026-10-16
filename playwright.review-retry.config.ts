import { defineConfig } from "@playwright/test";
import base from "./playwright.review.config";
export default defineConfig({
  ...base,
  use: { ...base.use, baseURL: "http://127.0.0.1:4186" },
  webServer: {
    command: `"${process.execPath}" --require ./scripts/windows-realpath-compat.cjs node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 4186 --strictPort`,
    port: 4186,
    reuseExistingServer: false,
  },
  outputDir: "test-results-review-retry",
  reporter: [
    ["list"],
    [
      "json",
      { outputFile: "docs/evidence/m0-m3-review-latest-retry-2026-10-08.json" },
    ],
  ],
});
