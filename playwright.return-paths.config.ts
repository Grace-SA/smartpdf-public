import { defineConfig } from "@playwright/test";
const port = process.env.SMARTPDF_RETURN_PORT ?? "4226";
const label = process.env.SMARTPDF_RETURN_LABEL ?? port;
if (!/^[a-z0-9-]+$/.test(label)) throw Error("Invalid report label");
if (!["4217", "4226"].includes(port)) throw Error("Invalid local preview");
export default defineConfig({
  testDir: "./tests",
  testMatch: "raster-return-paths.spec.ts",
  workers: 1,
  timeout: 120000,
  expect: { timeout: 30000 },
  use: {
    baseURL: "http://127.0.0.1:" + port,
    hasTouch: true,
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { browserName: "chromium" } },
    { name: "webkit", use: { browserName: "webkit" } },
  ],
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/return-paths-" + label + ".json" }],
  ],
  outputDir: "test-results-return-paths-" + label,
});
