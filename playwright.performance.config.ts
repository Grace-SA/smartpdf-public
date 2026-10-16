import base from "./playwright.ux.config";
import { defineConfig } from "@playwright/test";
export default defineConfig({
  ...base,
  testMatch: ["ux-performance.spec.ts"],
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
  use: { ...base.use, trace: "off", screenshot: "off", video: "off" },
  reporter: [["list"]],
});
