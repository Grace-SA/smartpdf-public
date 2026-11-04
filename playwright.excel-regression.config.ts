import { defineConfig } from "@playwright/test";
import base from "./playwright.github.config";
export default defineConfig({
  ...base,
  workers: 2,
  use: { ...base.use, baseURL: "http://127.0.0.1:4275" },
  webServer: {
    command:
      "node scripts/m12-fixtures.mjs --dense && node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 4275 --strictPort",
    port: 4275,
    reuseExistingServer: false,
  },
  reporter: [
    ["list"],
    ["json", { outputFile: ".research/excel/regression-results.json" }],
  ],
  outputDir: ".research/excel/regression-artifacts",
});
