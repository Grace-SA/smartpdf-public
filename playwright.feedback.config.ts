import base from "./playwright.ux.config";
import { defineConfig } from "@playwright/test";
export default defineConfig({
  ...base,
  testMatch: [
    "ux-feedback.spec.ts",
    "ux-production.spec.ts",
    "ux-results.spec.ts",
  ],
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/ux5-feedback-tests.json" }],
  ],
});
