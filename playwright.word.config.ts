import { defineConfig } from "@playwright/test";
import base from "./playwright.github.config";
export default defineConfig({
  ...base,
  testMatch: ["word.spec.ts"],
  reporter: [
    ["list"],
    ["json", { outputFile: ".research/m13/word-browser-results.json" }],
  ],
  outputDir: ".research/m13/word-browser-artifacts",
});
