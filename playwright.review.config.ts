import base from "./playwright.m10-full.config";
import { defineConfig } from "@playwright/test";
export default defineConfig({
  ...base,
  testMatch: [...(base.testMatch as string[]), "raster-colour.spec.ts"],
  use: { ...base.use, baseURL: "http://127.0.0.1:4225" },
  webServer: {
    command:
      "node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 4225 --strictPort",
    port: 4225,
    reuseExistingServer: false,
  },
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/m8-m10-review-browser.json" }],
  ],
  outputDir: "test-results-m8-m10-review",
});
