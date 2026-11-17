import { defineConfig } from "@playwright/test";
const apiPort = Number(process.env.PDF_EXCEL_PORT || 4290);
const previewPort = Number(process.env.PDF_EXCEL_PREVIEW_PORT || 4291);
export default defineConfig({
  testDir: "./tests",
  testMatch: "pdf-to-excel.spec.ts",
  timeout: 60000,
  expect: { timeout: 30000 },
  workers: 1,
  reporter: [
    ["list"],
    ["json", { outputFile: "test-results-pdf-excel/report.json" }],
  ],
  use: {
    baseURL: `http://127.0.0.1:${previewPort}`,
    browserName:
      process.env.PDF_EXCEL_BROWSER === "webkit" ? "webkit" : "chromium",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { viewport: { width: 1280, height: 900 } } },
    {
      name: "mobile",
      use: {
        viewport: { width: 390, height: 844 },
        isMobile: true,
        hasTouch: true,
      },
    },
  ],
  webServer: [
    {
      command: "node server/pdf-to-excel/service.mjs",
      port: apiPort,
      reuseExistingServer: false,
    },
    {
      command: `node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port ${previewPort} --strictPort`,
      port: previewPort,
      env: { PDF_EXCEL_API_TARGET: `http://127.0.0.1:${apiPort}` },
      reuseExistingServer: false,
    },
  ],
});
