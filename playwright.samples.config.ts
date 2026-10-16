import { defineConfig } from "@playwright/test";
const channel = process.env.SMARTWORKS_BROWSER_CHANNEL;
if (channel && !["chrome", "msedge"].includes(channel))
  throw new Error("Unsupported sample browser channel");
const suffix = channel ? `-${channel}` : "";
export default defineConfig({
  testDir: "./scripts",
  testMatch: "real-preview.spec.ts",
  timeout: 120000,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:4186",
    browserName: "chromium",
    ...(channel ? { channel } : {}),
    trace: "off",
    screenshot: "off",
    video: "off",
  },
  reporter: [
    ["list"],
    ["json", { outputFile: `docs/private-samples/browser-test${suffix}.json` }],
  ],
  outputDir: "docs/private-samples/browser-output",
  webServer: {
    command:
      "node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 4186 --strictPort",
    port: 4186,
    reuseExistingServer: false,
  },
});
