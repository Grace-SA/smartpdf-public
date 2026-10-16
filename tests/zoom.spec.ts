import { test, expect, chromium } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import { makeFixture } from "./fixtures";

test("real browser 200 percent zoom preserves controls and preview", async ({
  browserName,
}, info) => {
  expect(browserName).toBe("chromium");
  const profile = info.outputPath("zoom-profile");
  await mkdir(`${profile}/Default`, { recursive: true });
  // Chromium's native profile zoom preference. Only this isolated test profile
  // is changed. Empty storage partition key is "x"; zoom factor = 1.2 ** level.
  // https://raw.githubusercontent.com/chromium/chromium/main/chrome/browser/ui/zoom/chrome_zoom_level_prefs.cc
  await writeFile(
    `${profile}/Default/Preferences`,
    JSON.stringify({
      partition: { default_zoom_level: { x: Math.log(2) / Math.log(1.2) } },
    }),
  );
  const channel = process.env.SMARTWORKS_ZOOM_CHANNEL ?? "chromium";
  const context = await chromium.launchPersistentContext(profile, {
    channel,
    headless: true,
    viewport: { width: 1280, height: 900 },
  });
  try {
    const page = await context.newPage();
    await page.goto("http://127.0.0.1:4185/");
    await expect(page.getByText("Ready for local processing")).toBeVisible();
    await expect.poll(() => page.evaluate(() => innerWidth)).toBe(640);
    expect(await page.evaluate(() => devicePixelRatio)).toBe(2);
    expect(await page.evaluate(() => visualViewport!.scale)).toBe(1);
    await page.locator("#pdf-file").setInputFiles({
      name: "zoom.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from(await makeFixture()),
    });
    await expect(page.getByText("Page 1 of 2", { exact: true })).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.getByRole("button", { name: "Next" }).click();
    await expect(page.getByText("Page 2 of 2", { exact: true })).toBeVisible();
    // Full-page/scrolled clips are unreliable under native zoom in this driver.
    // Keep a top-viewport illustration; the interaction assertions above are
    // the evidence for controls, rather than claiming the picture shows them.
    await page.evaluate(() => window.scrollTo(0, 0));
    await expect.poll(() => page.evaluate(() => scrollY)).toBe(0);
    await page.screenshot({ path: "docs/evidence/zoom-200.png" });
    await page.getByRole("button", { name: "Clear session" }).click();
    await expect(page.locator("canvas")).toHaveCount(0);
    await writeFile(
      "docs/evidence/zoom-200.json",
      JSON.stringify(
        {
          zoom: 2,
          channel,
          browserVersion: context.browser()?.version(),
          viewport: 1280,
          innerWidth: await page.evaluate(() => innerWidth),
          devicePixelRatio: await page.evaluate(() => devicePixelRatio),
          visualViewportScale: await page.evaluate(() => visualViewport!.scale),
          verified: ["no horizontal overflow", "next page", "clear session"],
          method:
            "native profile page-zoom preference in an isolated browser profile; verified CSS viewport halving and DPR doubling, pinch scale remains 1",
        },
        null,
        2,
      ),
    );
  } finally {
    await context.close();
  }
});
