import base from "./playwright.journeys.config";
import { defineConfig } from "@playwright/test";
export default defineConfig({
  ...base,
  testMatch: [...(base.testMatch as string[]), "ux-leave.spec.ts"],
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/ux8-regression.json" }],
  ],
});
