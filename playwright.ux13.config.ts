import base from "./playwright.completion.config";
import { defineConfig } from "@playwright/test";
export default defineConfig({
  ...base,
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/ux13-regression.json" }],
  ],
});
