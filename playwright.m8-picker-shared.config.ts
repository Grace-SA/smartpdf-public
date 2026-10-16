import base from "./playwright.m8-picker.config";
import { defineConfig } from "@playwright/test";
export default defineConfig({
  ...base,
  testMatch: [
    "task-boundaries.spec.ts",
    "ux-leave.spec.ts",
    "loading-navigation.spec.ts",
  ],
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/m8-picker-shared-regression.json" }],
  ],
  outputDir: "test-results-m8-picker-shared",
  use: { ...base.use, baseURL: "http://127.0.0.1:4219" },
  webServer: {
    command:
      "node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 4219 --strictPort",
    port: 4219,
    reuseExistingServer: false,
  },
});
