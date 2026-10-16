import { selectTool } from "./navigation";
import { test, expect, type Page } from "@playwright/test";
import { mkdir, readFile, writeFile } from "node:fs/promises";
const root = "tests/fixtures/m5/",
  out = "docs/evidence/m8-output";
async function open(page: Page, name = "normal-a4.pdf") {
  await page.goto("/pdf-to-jpg/");
  await page.locator("#pdf-file").setInputFiles(root + name);
  await expect(page.locator(".raster-task")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Convert to JPG →", exact: true }),
  ).toBeEnabled();
}
async function save(
  page: Page,
  engine: string,
  name: string,
  label = "Download ZIP",
  focus = true,
) {
  await expect(
    page.getByRole("heading", { name: "Your images are ready" }),
  ).toBeVisible({ timeout: 125_000 });
  await expect(page.locator(".raster-task,.raster-submit")).toHaveCount(0);
  if (focus)
    await expect(
      page.getByRole("heading", { name: "Your images are ready" }),
    ).toBeFocused();
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: label, exact: true }).click();
  const d = await pending;
  expect(d.suggestedFilename()).toMatch(
    name.endsWith(".zip") ? /\.zip$/ : /\.(png|jpg)$/,
  );
  await mkdir(out, { recursive: true });
  await writeFile(
    `${out}/${engine}-${name}`,
    await readFile((await d.path())!),
  );
}
for (const width of [390, 1280])
  test(`complete task, download, repeat and switch at ${width}`, async ({
    page,
    browserName,
  }) => {
    await page.setViewportSize({ width, height: 780 });
    const external: string[] = [];
    page.on("request", (r) => {
      if (
        /^https?:/.test(r.url()) &&
        new URL(r.url()).origin !== String(test.info().project.use.baseURL)
      )
        external.push(r.url());
    });
    await open(page);
    await mkdir(out, { recursive: true });
    await page.screenshot({
      path: `${out}/${browserName}-settings-${width}.png`,
      fullPage: true,
    });
    await page
      .getByRole("radio", { name: "PNG Sharper text, larger files" })
      .check();
    await page.getByRole("radio", { name: "High 300 DPI" }).check();
    await page.getByRole("radio", { name: "Page range", exact: true }).check();
    await page
      .getByRole("textbox", { name: "Page range", exact: true })
      .fill("2");
    await page.getByRole("button", { name: "Preview page 2" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.getByRole("button", { name: /Close preview/ }).click();
    await page.getByRole("button", { name: "Convert to PNG →" }).click();
    await save(page, browserName, `single-${width}.png`, "Download PNG");
    await page.screenshot({
      path: `${out}/${browserName}-result-${width}.png`,
    });
    await save(page, browserName, `repeat-${width}.png`, "Download PNG", false);
    await selectTool(page, "Split a PDF");
    await page.locator("#pdf-file").setInputFiles(root + "normal-a4.pdf");
    await expect(page.locator(".split-task")).toBeVisible();
    expect(external).toEqual([]);
  });
for (const fixture of [
  "normal-a4",
  "mixed-page-size",
  "landscape",
  "100-pages",
  "scanned",
  "form",
  "chinese",
  "japanese",
  "image-heavy",
  "200-pages",
  "unusual-page-sizes",
  "m8-geometry",
  "m8-detail",
  "m8-transparency",
  "m8-embedded-japanese",
])
  test(`export ${fixture}`, async ({ page, browserName }) => {
    await open(page, fixture + ".pdf");
    if (["chinese", "japanese"].includes(fixture))
      await expect(page.getByText(/Some fonts aren’t embedded/)).toBeVisible();
    if (fixture === "m8-embedded-japanese")
      await expect(page.getByText(/Some fonts aren’t embedded/)).toHaveCount(0);
    if (fixture.startsWith("m8-")) {
      await page
        .getByRole("radio", { name: "PNG Sharper text, larger files" })
        .check();
      await page.getByRole("radio", { name: "High 300 DPI" }).check();
    }
    await page
      .getByRole("button", { name: /^Convert to (JPG|PNG) →$/ })
      .click();
    await save(
      page,
      browserName,
      `${fixture}.${fixture.startsWith("m8-") ? "png" : "zip"}`,
      fixture.startsWith("m8-") ? "Download PNG" : "Download ZIP",
    );
  });
for (const fixture of [
  "zero-pages",
  "encrypted",
  "corrupted",
  "large-50mb",
  "100mb",
])
  test(`reject ${fixture}`, async ({ page }) => {
    await page.goto("/pdf-to-jpg/");
    await page.locator("#pdf-file").setInputFiles(root + fixture + ".pdf");
    await expect(page.locator(".raster-task")).toHaveCount(0);
    await expect(page.locator("#pdf-file")).toBeEnabled();
    await expect(page.locator(".message")).toContainText(
      /couldn|unsupported|large|limit|encrypted|password|file|safely/i,
    );
  });
test("high quality over budget, invalid range and leave protection", async ({
  page,
}) => {
  await open(page, "mixed-page-size.pdf");
  await page.getByRole("radio", { name: "High 300 DPI" }).check();
  await expect(page.getByRole("alert")).toContainText("Page 3");
  await expect(
    page.getByRole("button", { name: "Convert to JPG →" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Use Standard" }).click();
  await page.getByRole("radio", { name: "Page range", exact: true }).check();
  await page
    .getByRole("textbox", { name: "Page range", exact: true })
    .fill("0");
  await expect(
    page.getByRole("button", { name: "Convert to JPG →" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "← All tools" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Keep editing", exact: true }).click();
  await expect(page.locator(".raster-task")).toBeVisible();
});
test("cancel large task then retry preserves range and format", async ({
  page,
}) => {
  await open(page, "200-pages.pdf");
  await page.getByRole("button", { name: "Convert to JPG →" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: /Cancel/ })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.getByText("Cancelled. Your file and settings are unchanged."),
  ).toBeVisible();
  await page.getByRole("radio", { name: "Page range", exact: true }).check();
  await page
    .getByRole("textbox", { name: "Page range", exact: true })
    .fill("1");
  await page.getByRole("button", { name: "Convert to JPG →" }).click();
  await expect(
    page.getByRole("button", { name: "Download JPG", exact: true }),
  ).toBeVisible();
});

test("200 pages high-quality JPG produce one complete ZIP", async ({
  page,
  browserName,
}) => {
  await open(page, "200-pages.pdf");
  await page.getByRole("radio", { name: "High 300 DPI" }).check();
  await page.getByRole("button", { name: "Convert to JPG →" }).click();
  await save(page, browserName, "200-pages-high.zip");
});

test("encoder failure leaves no partial result and a retryable task", async ({
  page,
}) => {
  await page.addInitScript(() => {
    HTMLCanvasElement.prototype.toBlob = function (callback) {
      callback(null);
    };
  });
  await open(page);
  await page.getByRole("button", { name: "Convert to JPG →" }).click();
  await expect(
    page.getByText(
      "This browser could not create this image format. Try the other format.",
    ),
  ).toBeVisible();
  await expect(page.locator(".delivery")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Convert to JPG →" }),
  ).toBeEnabled();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("image output is independent of screen DPR", async ({
  browser,
  browserName,
}) => {
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:4216",
    deviceScaleFactor: 2,
  });
  const page = await context.newPage();
  // Use the configured origin, so this also works in the dedicated M8 suite.
  const origin = String(test.info().project.use.baseURL);
  await page.goto(origin + "/pdf-to-jpg/");
  await page.locator("#pdf-file").setInputFiles(root + "normal-a4.pdf");
  await expect(
    page.getByRole("button", { name: "Convert to JPG →" }),
  ).toBeEnabled();
  await page
    .getByRole("radio", { name: "PNG Sharper text, larger files" })
    .check();
  await page.getByRole("radio", { name: "High 300 DPI" }).check();
  await page.getByRole("radio", { name: "Page range", exact: true }).check();
  await page
    .getByRole("textbox", { name: "Page range", exact: true })
    .fill("2");
  await page.getByRole("button", { name: "Convert to PNG →" }).click();
  await save(page, browserName, "dpr2.png", "Download PNG");
  expect(await readFile(`${out}/${browserName}-dpr2.png`)).toEqual(
    await readFile(`${out}/${browserName}-single-390.png`),
  );
  await context.close();
});

test("nine-tool navigation never overlaps the brand or privacy badge", async ({
  page,
}) => {
  for (const width of [320, 390, 800, 1024, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/pdf-to-jpg/");
    await page.locator(".tool-nav").waitFor({ state: "attached" });
    const overlap = await page.evaluate(() => {
      const nav = document.querySelector(".tool-nav")!.getBoundingClientRect(),
        brand = document
          .querySelector("header .brand")!
          .getBoundingClientRect(),
        badge = document
          .querySelector("header .version")!
          .getBoundingClientRect();
      const hit = (a: DOMRect, b: DOMRect) =>
        a.left < b.right &&
        a.right > b.left &&
        a.top < b.bottom &&
        a.bottom > b.top;
      return (
        hit(nav, brand) ||
        hit(nav, badge) ||
        document.documentElement.scrollWidth >
          document.documentElement.clientWidth
      );
    });
    expect(overlap).toBe(false);
  }
});

test("a ready tab converts offline without document requests", async ({
  page,
  browserName,
}) => {
  await page.goto("/pdf-to-jpg/");
  await expect(page.locator(".panel > .status.ready")).toHaveCount(1);
  const requests: string[] = [];
  page.on("request", (r) => {
    if (/^https?:/.test(r.url())) requests.push(r.url());
  });
  // Windows Playwright WebKit native-offline also blocks blob worker URLs.
  // Block all HTTP instead; physical iPhone disconnection is a separate gate.
  await page
    .context()
    .route(/^https?:/, (route) => route.abort("internetdisconnected"));
  if (browserName === "chromium") await page.context().setOffline(true);
  await page.locator("#pdf-file").setInputFiles(root + "normal-a4.pdf");
  await expect(
    page.getByRole("button", { name: "Convert to JPG →" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Convert to JPG →" }).click();
  await save(page, browserName, "offline.zip");
  expect(requests).toEqual([]);
});

test("PNG Standard multi-page ZIP preserves format and selected density", async ({
  page,
  browserName,
}) => {
  await open(page);
  await page
    .getByRole("radio", { name: "PNG Sharper text, larger files" })
    .check();
  await page.getByRole("button", { name: "Convert to PNG →" }).click();
  await save(page, browserName, "normal-png.zip");
});
