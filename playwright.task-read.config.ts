import base from "./playwright.ux.config";
import { defineConfig } from "@playwright/test";
export default defineConfig({
  ...base,
  testMatch: "task-read-consent.spec.ts",
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/ux10-read-consent.json" }],
  ],
});
