import { defineConfig } from "@playwright/test";
import base from "./playwright.config";
// Windows WebKit is diagnostic coverage, never a substitute for iOS/Safari.
export default defineConfig({
  ...base,
  testMatch: [
    "legacy-preview.spec.ts",
    "resource-preview.spec.ts",
    "passive-preview.spec.ts",
  ],
  use: { ...base.use, browserName: "webkit" },
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/webkit-diagnostic-results.json" }],
  ],
});
