import { defineConfig } from "@playwright/test";
import base from "./playwright.config";
export default defineConfig({
  ...base,
  testMatch: [
    "passive-preview.spec.ts",
    "desktop-checks.spec.ts",
    "legacy-preview.spec.ts",
    "engine-lifecycle.spec.ts",
    "photos.spec.ts",
    "combine.spec.ts",
  ],
  grepInvert: /M1 ten 2MP/,
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/desktop-browser-results.json" }],
  ],
  projects: [
    { name: "chrome", use: { channel: "chrome" } },
    { name: "edge", use: { channel: "msedge" } },
  ],
});
