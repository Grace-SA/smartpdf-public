import base from "./playwright.navigation.config";
import { defineConfig } from "@playwright/test";
export default defineConfig({
  ...base,
  testMatch: [
    "loading-navigation.spec.ts",
    "raster-picker.spec.ts",
    "responsive-navigation.spec.ts",
    "ux-picker-dialog.spec.ts",
    "task-boundaries.spec.ts",
    "ux-leave.spec.ts",
    "seo.spec.ts",
    "raster.spec.ts",
    "sign.spec.ts",
    "compress.spec.ts",
    "rotate.spec.ts",
    "ux-preview-stability.spec.ts",
    "task-read-consent.spec.ts",
  ],
  grep: /(?:loading-navigation|raster-picker|responsive-navigation|ux-picker-dialog|task-boundaries|ux-leave|seo)\.spec\.ts|complete task, download|Image and phone task guards|mobile layout|recommended is the default|image and generated PDF previews|copy preparation|task preview|consent prepares|completion returns/,
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/responsive-navigation-final.json" }],
  ],
  outputDir: "test-results-responsive-navigation-final",
});
