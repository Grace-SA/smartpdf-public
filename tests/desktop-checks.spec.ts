import { expect, test } from "@playwright/test";
import { writeFile } from "node:fs/promises";
import { passiveFixture } from "./passive-fixture";

test("cold shell and resource readiness are measured separately at 10Mbps/100ms", async ({
  browser,
}, info) => {
  const samples = [];
  for (let i = 0; i < 3; i++) {
    const context = await browser.newContext();
    const page = await context.newPage();
    const cdp = await context.newCDPSession(page);
    await cdp.send("Network.enable");
    await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
    await cdp.send("Network.emulateNetworkConditions", {
      offline: false,
      latency: 100,
      downloadThroughput: 10_000_000 / 8,
      uploadThroughput: 10_000_000 / 8,
    });
    const started = performance.now();
    await page.goto("http://127.0.0.1:4185/", {
      waitUntil: "domcontentloaded",
    });
    await expect(
      page.getByRole("heading", { name: "Your PDF, just here." }),
    ).toBeVisible();
    await page.getByText("Which PDFs can I open?", { exact: true }).click();
    await expect(
      page.getByText(/links and comment popups are not interactive/),
    ).toBeVisible();
    const shellMs = performance.now() - started;
    await expect(page.getByText("Ready for local processing")).toBeVisible({
      timeout: 30000,
    });
    samples.push({ shellMs, readyMs: performance.now() - started });
    await context.close();
  }
  await writeFile(
    `docs/evidence/cold-${info.project.name || "chromium"}.json`,
    JSON.stringify(
      {
        browser: browser.version(),
        samples,
        network:
          "CDP simulated 10Mbps/100ms; new context and cache disabled; local host",
        measured:
          "shell heading plus working disclosure; file processing awaits ready",
      },
      null,
      2,
    ),
  );
  // A measured regression, not an invented network or low-end device result.
  expect(Math.max(...samples.map((s) => s.shellMs))).toBeLessThanOrEqual(3000);
});

test("portrait to landscape preserves the loaded document without horizontal overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await page.locator("#pdf-file").setInputFiles({
    name: "orientation.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from(await (await passiveFixture()).save()),
  });
  await expect(page.getByText("Page 1 of 1", { exact: true })).toBeVisible();
  for (const viewport of [
    { width: 390, height: 844 },
    { width: 844, height: 390 },
  ]) {
    await page.setViewportSize(viewport);
    await expect(page.locator("canvas")).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await expect(
      page.getByRole("button", { name: "Clear session" }),
    ).toBeEnabled();
  }
});
