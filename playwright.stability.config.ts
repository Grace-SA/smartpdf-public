import base from "./playwright.ux.config";
import { defineConfig } from "@playwright/test";
export default defineConfig({
  ...base,
  testMatch: "ux-preview-stability.spec.ts",
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/ux7-stability.json" }],
  ],
});
