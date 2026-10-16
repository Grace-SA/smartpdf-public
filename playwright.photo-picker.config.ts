import { defineConfig } from "@playwright/test";
import base from "./playwright.heic.config";
export default defineConfig({
  ...base,
  use: {
    ...base.use,
    baseURL: process.env.SMARTWORKS_TEST_BASE_URL ?? "http://127.0.0.1:4185",
  },
  testMatch: ["**/photo-files-picker.spec.ts"],
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/heic-files-picker-2026-10-08.json" }],
  ],
});
