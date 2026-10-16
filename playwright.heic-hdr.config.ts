import { defineConfig } from "@playwright/test";
import base from "./playwright.heic.config";
export default defineConfig({
  ...base,
  use: { ...base.use, baseURL: "http://127.0.0.1:4199" },
  testMatch: ["**/heic-real-local.spec.ts", "**/heic.spec.ts"],
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/heic-hdr-browser-2026-10-08.json" }],
  ],
});
