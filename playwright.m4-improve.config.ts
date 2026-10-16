import { defineConfig } from "@playwright/test";
import base from "./playwright.mobile-harness.config";
export default defineConfig({
  ...base,
  testMatch: ["**/credential-copy.spec.ts", "**/split.spec.ts"],
  use: { ...base.use, baseURL: "http://127.0.0.1:4187" },
  webServer: {
    command:
      "node --require ./scripts/windows-realpath-compat.cjs node_modules/vite/bin/vite.js preview --outDir dist-m4-improve --host 127.0.0.1 --port 4187 --strictPort",
    port: 4187,
    reuseExistingServer: false,
  },
  outputDir: "test-results-m4-improve",
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/m4-improve-browser.json" }],
  ],
});
