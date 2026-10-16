import base from "./playwright.m10-full.config";
import { defineConfig } from "@playwright/test";
export default defineConfig({
  ...base,
  testMatch: ["raster-colour.spec.ts"],
  workers: 1,
  use: { ...base.use, baseURL: "http://127.0.0.1:4224" },
  webServer: {
    command:
      "node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 4224 --strictPort",
    port: 4224,
    reuseExistingServer: false,
  },
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/colour-regression.json" }],
  ],
  outputDir: "test-results-colour",
});
