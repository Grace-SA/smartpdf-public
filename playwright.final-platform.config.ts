import { defineConfig } from "@playwright/test";
import base from "./playwright.config";
export default defineConfig({
  ...base,
  webServer: undefined,
  testMatch: [
    "final-compatibility.spec.ts",
    "output-intents.spec.ts",
    "closing-compatibility.spec.ts",
  ],
  projects: [
    { name: "chrome", use: { channel: "chrome" } },
    { name: "edge", use: { channel: "msedge" } },
    { name: "webkit", use: { browserName: "webkit" } },
  ],
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/m2-final95-platforms.json" }],
  ],
});
