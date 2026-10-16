import base from "./playwright.journeys.config";
import { defineConfig } from "@playwright/test";
export default defineConfig({
  ...base,
  testMatch: [...(base.testMatch as string[]), "ux-preview-stability.spec.ts"],
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/ux7-regression.json" }],
  ],
});
