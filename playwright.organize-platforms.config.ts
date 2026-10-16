import { defineConfig } from "@playwright/test";
import base from "./playwright.organize.config";
export default defineConfig({
  ...base,
  projects: [
    { name: "chrome", use: { channel: "chrome" } },
    { name: "edge", use: { channel: "msedge" } },
    { name: "webkit", use: { browserName: "webkit" } },
  ],
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/m3-platforms.json" }],
  ],
});
