import { defineConfig } from "@playwright/test";
import base from "./playwright.final-platform.config";
export default defineConfig({
  ...base,
  testMatch: [
    "jpeg-resource.spec.ts",
    "final-compatibility.spec.ts",
    "ordinary-compatibility.spec.ts",
  ],
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/m2-resource-fix-platforms.json" }],
  ],
});
