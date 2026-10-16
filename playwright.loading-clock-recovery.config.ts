import base from "./playwright.production-loading-fix.config";
import { defineConfig } from "@playwright/test";
export default defineConfig({
  ...base,
  testMatch: ["watermark-shell.spec.ts"],
  grep: /a slow first CJK/,
  use: { ...base.use, baseURL: "http://127.0.0.1:4234" },
  webServer: {
    command:
      "node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 4234 --strictPort",
    port: 4234,
    reuseExistingServer: false,
  },
  reporter: [
    ["list"],
    [
      "json",
      {
        outputFile:
          "releases/20261016-grouped-navigation/loading-clock-recovery.json",
      },
    ],
  ],
  outputDir: "test-results-loading-clock-recovery",
});
