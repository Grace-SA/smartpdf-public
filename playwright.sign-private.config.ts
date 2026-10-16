import { defineConfig } from "@playwright/test";
import { signPrivateFolder } from "./scripts/sign-private-path";
export default defineConfig({
  testDir: "./scripts",
  testMatch: "sign-private.spec.ts",
  workers: 1,
  timeout: 120000,
  use: {
    baseURL: "http://127.0.0.1:4205",
    viewport: { width: 1280, height: 900 },
    trace: "off",
  },
  projects: [
    { name: "chromium", use: { browserName: "chromium" } },
    { name: "webkit", use: { browserName: "webkit" } },
  ],
  reporter: [
    ["list"],
    ["json", { outputFile: `${signPrivateFolder}/browser.json` }],
  ],
  outputDir: `${signPrivateFolder}/browser-output`,
});
