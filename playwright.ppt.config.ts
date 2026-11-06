import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  testMatch: "ppt.spec.ts",
  timeout: 60000,
  workers: 1,
  reporter: [["list"], ["json", { outputFile: ".research/ppt/browser.json" }]],
  outputDir: ".research/ppt/browser-artifacts",
  use: { baseURL: "http://127.0.0.1:4280", trace: "off" },
  projects: [
    { name: "chromium", use: { browserName: "chromium" } },
    { name: "webkit", use: { browserName: "webkit" } },
  ],
  webServer: {
    command:
      "node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 4280 --strictPort",
    port: 4280,
    reuseExistingServer: false,
  },
});
