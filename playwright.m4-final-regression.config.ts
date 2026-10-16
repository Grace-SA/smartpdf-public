import { defineConfig } from "@playwright/test";
import base from "./playwright.m4-regression.config";
export default defineConfig({
  ...base,
  use: { ...base.use, baseURL: "http://127.0.0.1:4188" },
  webServer: {
    command: `"${process.execPath}" --require ./scripts/windows-realpath-compat.cjs node_modules/vite/bin/vite.js preview --outDir dist-m4-final --host 127.0.0.1 --port 4188 --strictPort`,
    port: 4188,
    reuseExistingServer: false,
  },
  outputDir: "test-results-m4-final-regression",
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/m4-final-regression.json" }],
  ],
});
