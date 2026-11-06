import { defineConfig } from "@playwright/test";
import base from "./playwright.github.config";
export default defineConfig({
  ...base,
  testMatch: ["excel.spec.ts", "word.spec.ts"],
  workers: 1,
  use: { ...base.use, baseURL: "http://127.0.0.1:4275" },
  webServer: {
    command:
      "node node_modules/vite/bin/vite.js preview --outDir dist-excel-final --host 127.0.0.1 --port 4275 --strictPort",
    port: 4275,
    reuseExistingServer: false,
  },
  reporter: [
    ["list"],
    ["json", { outputFile: ".research/excel/browser-results.json" }],
  ],
  outputDir: ".research/excel/browser-artifacts",
});
