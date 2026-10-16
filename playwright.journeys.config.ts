import base from "./playwright.feedback.config";
import { defineConfig } from "@playwright/test";
export default defineConfig({
  ...base,
  testMatch: [
    "ux-feedback.spec.ts",
    "ux-production.spec.ts",
    "ux-results.spec.ts",
    "ux-journeys.spec.ts",
  ],
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/ux6-regression.json" }],
  ],
});
