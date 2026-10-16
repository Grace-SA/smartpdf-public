import base from "./playwright.leave.config";
import { defineConfig } from "@playwright/test";
export default defineConfig({
  ...base,
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/ux8-final-review.json" }],
  ],
});
