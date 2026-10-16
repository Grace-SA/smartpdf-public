import base from "./playwright.ux.config";
import { defineConfig } from "@playwright/test";
export default defineConfig({
  ...base,
  testMatch: [
    "task-boundaries.spec.ts",
    "task-read-consent.spec.ts",
    "ux-leave.spec.ts",
    "ux-preview-stability.spec.ts",
  ],
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/ux12-regression.json" }],
  ],
});
