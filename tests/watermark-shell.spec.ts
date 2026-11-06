import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { PDFDocument, PDFName } from "pdf-lib";

for (const kind of ["ordinary", "credentials"] as const)
  test(`${kind} watermark requires explicit ordinary-copy consent`, async ({
    page,
  }) => {
    await page.goto("/watermark-pdf/");
    await page
      .locator("#pdf-file")
      .setInputFiles(`tests/fixtures/split/${kind}.pdf`);
    const dialog = page.getByRole("dialog", {
      name:
        kind === "ordinary"
          ? "Create an ordinary PDF copy"
          : "Create a copy without Content Credentials",
      exact: true,
    });
    await expect(dialog).toBeVisible();
    await expect(page.locator(".watermark-task,.delivery")).toHaveCount(0);
    await dialog
      .getByRole("button", {
        name:
          kind === "ordinary"
            ? "Create ordinary copy without standard claims"
            : "Create copy without credentials",
        exact: true,
      })
      .click();
    await expect(
      page.getByRole("button", { name: "Add watermark →", exact: true }),
    ).toBeEnabled();
    await expect(page.locator(".delivery")).toHaveCount(0);
    await page
      .getByRole("button", { name: "Add watermark →", exact: true })
      .click();
    const pending = page.waitForEvent("download");
    await page
      .getByRole("button", { name: "Download PDF", exact: true })
      .click();
    const bytes = await readFile((await (await pending).path())!);
    const result = await PDFDocument.load(bytes, { updateMetadata: false });
    expect(result.catalog.get(PDFName.of("AF"))).toBeUndefined();
    await expect(
      page.locator(".watermark-task,.watermark-actions"),
    ).toHaveCount(0);
  });

test("ordinary color profiles do not require standard-removal consent", async ({
  page,
}) => {
  await page.goto("/watermark-pdf/");
  await page
    .locator("#pdf-file")
    .setInputFiles("tests/fixtures/combine/final-color.pdf");
  await expect(
    page.getByRole("button", { name: "Add watermark →", exact: true }),
  ).toBeEnabled();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("home never requests the watermark font", async ({ page }) => {
  const requests: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes("/watermark-fonts/")) requests.push(r.url());
  });
  await page.goto("/");
  await expect(page.locator(".tool-home")).toBeVisible();
  await page.waitForTimeout(1000);
  expect(requests).toEqual([]);
});

test("font preparation is silent and keeps the native picker stable", async ({
  page,
}) => {
  let release!: () => void;
  const barrier = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/watermark-fonts/*.ttf", async (route) => {
    await barrier;
    await route.continue();
  });
  await page.goto("/watermark-pdf/");
  const label = page.locator('label[for="pdf-file"]');
  await expect(label).toBeVisible();
  const before = (await label.boundingBox())!;
  await expect(page.locator(".panel > .status")).toBeHidden();
  const chooser = page.waitForEvent("filechooser");
  await label.click();
  await (await chooser).setFiles([]);
  release();
  await expect(page.locator(".status.ready")).toHaveCount(1);
  const after = (await label.boundingBox())!;
  expect(Math.abs(after.x - before.x)).toBeLessThanOrEqual(1);
  expect(Math.abs(after.y - before.y)).toBeLessThanOrEqual(1);
  expect(after.height).toBe(before.height);
  await expect(page.locator(".panel > .status")).toBeHidden();
});

test("files selected while the font is delayed open without reselection", async ({
  page,
}) => {
  let release!: () => void;
  const barrier = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/watermark-fonts/*.ttf", async (route) => {
    await barrier;
    await route.continue();
  });
  await page.goto("/watermark-pdf/");
  const chooser = page.waitForEvent("filechooser");
  await page.locator("#pdf-file").click();
  await (await chooser).setFiles("tests/fixtures/m8-device.pdf");
  release();
  await expect(page.locator(".watermark-task")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Add watermark →", exact: true }),
  ).toBeEnabled();
});

test("font download failure retries without selecting the PDF again", async ({
  page,
}) => {
  let attempts = 0;
  await page.route("**/watermark-fonts/*.ttf", async (route) => {
    if (++attempts === 1)
      await route.fulfill({ status: 503, body: "Unavailable" });
    else await route.continue();
  });
  await page.goto("/watermark-pdf/");
  await page.locator("#pdf-file").setInputFiles("tests/fixtures/m8-device.pdf");
  await page
    .getByRole("button", { name: "Retry loading", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Add watermark →", exact: true }),
  ).toBeEnabled();
  expect(attempts).toBe(2);
});

test("editor toolbar, settings and footer fit small screens and landscape", async ({
  page,
}, info) => {
  await page.goto("/watermark-pdf/");
  await page.locator("#pdf-file").setInputFiles("tests/fixtures/m8-device.pdf");
  await expect(
    page.getByRole("button", { name: "Add watermark →", exact: true }),
  ).toBeEnabled();
  for (const [width, height] of [
    [320, 844],
    [390, 844],
    [844, 390],
    [768, 1024],
    [1024, 768],
    [1440, 900],
    [1920, 1080],
  ] as const) {
    await page.setViewportSize({ width, height });
    await page
      .getByRole("textbox", { name: "Watermark text", exact: true })
      .fill("REVIEW");
    const boxes = await page.evaluate(() => {
      const preview = document
        .querySelector(".watermark-preview")!
        .getBoundingClientRect();
      const toolbar = document
        .querySelector(".watermark-toolbar")!
        .getBoundingClientRect();
      const select = document
        .querySelector(".watermark-toolbar select")!
        .getBoundingClientRect();
      return {
        overflow: document.documentElement.scrollWidth > innerWidth,
        selectRight: select.right,
        toolbarRight: toolbar.right,
        previewWidth: preview.width,
      };
    });
    expect(boxes.overflow).toBe(false);
    expect(boxes.selectRight).toBeLessThanOrEqual(boxes.toolbarRight + 1);
    expect(boxes.previewWidth).toBeGreaterThan(200);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: info.outputPath(`watermark-${width}x${height}.png`),
    });
  }
});

test("a slow first CJK font download keeps the selected PDF beyond the ordinary startup deadline", async ({
  page,
}) => {
  await page.clock.install();
  let workersStarted = 0;
  page.on("worker", () => {
    workersStarted += 1;
  });
  let release!: () => void;
  let requested!: () => void;
  const barrier = new Promise<void>((resolve) => {
    release = resolve;
  });
  const started = new Promise<void>((resolve) => {
    requested = resolve;
  });
  await page.route("**/watermark-fonts/*.ttf", async (route) => {
    requested();
    await barrier;
    await route.continue();
  });
  await page.goto("/watermark-pdf/");
  await started;
  await page.locator("#pdf-file").setInputFiles("tests/fixtures/m8-device.pdf");
  // Resource warming no longer starts canaries. A selected file waits for the
  // font before any document worker, so advancing timers cannot expire boot.
  expect(workersStarted).toBe(0);
  await page.clock.fastForward(45000);
  await expect(page.locator(".status.error")).toHaveCount(0);
  await expect(page.locator(".watermark-task")).toHaveCount(0);
  expect(workersStarted).toBe(0);
  await page.clock.resume();
  release();
  await expect(page.locator(".watermark-task")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Add watermark →", exact: true }),
  ).toBeEnabled();
});
