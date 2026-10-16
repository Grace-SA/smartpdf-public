import { defineConfig } from "@playwright/test";
import { join } from "node:path";
export default defineConfig({
  testDir: "./scripts",
  testMatch: "corpus-preview.spec.ts",
  timeout: 1200000,
  workers: 1,
  use: {
    actionTimeout: 15000,
    navigationTimeout: 30000,
    baseURL: "http://127.0.0.1:4187",
    browserName: "chromium",
    trace: "off",
    screenshot: "off",
    video: "off",
  },
  outputDir: join(process.env.TEMP!, "smartworks-corpus-browser-runner"),
  reporter: "list",
  webServer:
    process.env.SMARTWORKS_TEST_EXTERNAL_SERVER === "1"
      ? undefined
      : {
          command:
            "node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 4187 --strictPort",
          port: 4187,
          reuseExistingServer: false,
        },
});
