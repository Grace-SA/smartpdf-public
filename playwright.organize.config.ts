import { defineConfig } from "@playwright/test";
import base from "./playwright.config";
export default defineConfig({
  ...base,
  webServer: undefined,
  testMatch: "organize.spec.ts",
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/m3-browser.json" }],
  ],
});
