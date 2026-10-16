import base from "./playwright.ux.config";
import { defineConfig } from "@playwright/test";
export default defineConfig({
  ...base,
  testMatch: "ux-picker-dialog.spec.ts",
  use: { ...base.use, hasTouch: true, isMobile: true },
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/ux13-picker.json" }],
  ],
});
