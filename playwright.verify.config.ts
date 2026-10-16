import config from "./playwright.config";
export default {
  ...config,
  webServer: undefined,
  reporter: [
    ["list"],
    [
      "json",
      {
        outputFile:
          process.env.SMARTWORKS_BROWSER_REPORT ||
          "docs/evidence/m2-ordinary-browser.json",
      },
    ],
  ],
};
