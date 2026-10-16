import base from "./playwright.grouped-navigation.config";
import { defineConfig } from "@playwright/test";
export default defineConfig({
  ...base,
  testMatch: ["responsive-navigation.spec.ts"],
  grep: /menu keyboard/,
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
      { outputFile: "docs/evidence/grouped-navigation-keyboard-recovery.json" },
    ],
  ],
  outputDir: "test-results-grouped-navigation-keyboard-recovery",
});
