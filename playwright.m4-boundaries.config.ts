import { defineConfig } from "@playwright/test";
import base from "./playwright.mobile-harness.config";
export default defineConfig({
  ...base,
  testMatch: "**/m4-boundaries.spec.ts",
  use: { ...base.use, baseURL: "http://127.0.0.1:4199" },
  outputDir: "test-results-m4-boundaries",
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/m4-boundaries.json" }],
  ],
});
