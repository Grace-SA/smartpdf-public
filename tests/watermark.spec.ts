import { test, expect, type Page } from "@playwright/test";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { PDFDocument } from "pdf-lib";
import { selectTool } from "./navigation";
import { pageGeometry } from "../src/overlay/geometry";
import {
  defaults,
  planWatermarks,
  type WatermarkSettings,
} from "../src/watermark/model";
import { textShape } from "../src/watermark/font";
const out = "docs/evidence/m10-browser-output";
const fontBytes = new Uint8Array(
  await readFile("public/watermark-fonts/SmartPDFSans-Regular.ttf"),
);
await mkdir(out, { recursive: true });
async function choose(page: Page, id: string, files: string[]) {
  const pending = page.waitForEvent("filechooser");
  await page.locator(`#${id}`).click();
  await (await pending).setFiles(files);
}
async function open(page: Page, file = "tests/fixtures/m8-device.pdf") {
  await page.goto("/watermark-pdf/");
  await choose(page, "pdf-file", [file]);
  await expect(
    page.getByRole("button", { name: "Add watermark →", exact: true }),
  ).toBeEnabled({ timeout: 30000 });
  await expect(
    page.locator('.watermark-sheet[data-page="1"] .sign-canvas canvas'),
  ).toBeVisible();
}
async function download(page: Page, name: string) {
  await expect(
    page.getByRole("heading", {
      name: "Your watermarked PDF is ready",
      exact: true,
    }),
  ).toBeInViewport();
  await expect(page.locator(".watermark-task,.watermark-actions")).toHaveCount(
    0,
  );
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PDF", exact: true }).click();
  const bytes = await readFile((await (await pending).path())!);
  await writeFile(`${out}/${name}.pdf`, bytes);
  const fixtures = [
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
  ];
  const fixture = fixtures.find((f) => name.endsWith("-" + f));
  const source = fixture
    ? `tests/fixtures/m5/${fixture}.pdf`
    : "tests/fixtures/m8-device.pdf";
  const original = await PDFDocument.load(await readFile(source), {
    updateMetadata: false,
  });
  const settings: WatermarkSettings = { ...defaults };
  let imageRatio = 1;
  if (/-text-\d+$/.test(name))
    Object.assign(settings, {
      text: "机密 DRAFT",
      range: "2",
      angle: -30,
      opacity: 40,
      position: 8,
    });
  else if (name.endsWith("-image-alpha")) {
    Object.assign(settings, { type: "image", angle: 0, opacity: 100 });
    imageRatio = 120 / 80;
  } else if (name.endsWith("-image-orientation")) {
    settings.type = "image";
    imageRatio = 60 / 100;
  } else if (name.endsWith("-repeat"))
    Object.assign(settings, {
      text: "REVIEW",
      layout: "repeat",
      size: 25,
      angle: 0,
      range: "1",
    });
  else if (name.endsWith("-cancel-retry")) settings.text = "KEEP DRAFT";
  else if (name.endsWith("-offline")) settings.text = "离线审核";
  const shape =
    settings.type === "text" ? textShape(fontBytes, settings.text) : null;
  await writeFile(
    `${out}/${name}.json`,
    JSON.stringify({
      source,
      settings,
      plan: planWatermarks(
        settings,
        original.getPages().map(pageGeometry),
        shape ? shape.width / shape.height : imageRatio,
      ),
    }),
  );
  return await PDFDocument.load(bytes);
}
for (const width of [390, 1440])
  test(`text range, preview, completion and next native picker at ${width}`, async ({
    page,
    browserName,
  }, info) => {
    await page.setViewportSize({ width, height: 900 });
    const external: string[] = [];
    page.on("request", (r) => {
      if (
        /^https?:/.test(r.url()) &&
        new URL(r.url()).origin !==
          new URL(String(info.project.use.baseURL)).origin
      )
        external.push(r.url());
    });
    await open(page);
    await page
      .getByRole("textbox", { name: "Watermark text", exact: true })
      .fill("机密 DRAFT");
    await page
      .getByRole("slider", { name: "Rotation", exact: true })
      .fill("-30");
    await page.getByRole("slider", { name: "Opacity", exact: true }).fill("40");
    await page
      .getByRole("button", { name: "Bottom right", exact: true })
      .click();
    await page.getByRole("radio", { name: "Page range", exact: true }).check();
    await page
      .getByRole("textbox", { name: "Page range", exact: true })
      .fill("2");
    await page
      .getByRole("textbox", { name: "Preview page", exact: true })
      .fill("2");
    await page.keyboard.press("Enter");
    await expect(
      page.locator('.watermark-sheet[data-page="2"] .watermark-overlay'),
    ).toHaveCount(1);
    await expect(
      page.locator('.watermark-sheet[data-page="1"] .watermark-overlay'),
    ).toHaveCount(0);
    await page.screenshot({
      path: info.outputPath(`watermark-edit-${width}.png`),
      fullPage: true,
    });
    await page
      .getByRole("button", { name: "Add watermark →", exact: true })
      .click();
    expect(
      (await download(page, `${browserName}-text-${width}`)).getPageCount(),
    ).toBe(2);
    await page.screenshot({
      path: info.outputPath(`watermark-result-${width}.png`),
    });
    await selectTool(page, "Split a PDF");
    await choose(page, "pdf-file", ["tests/fixtures/m8-device.pdf"]);
    await expect(page.locator(".split-task")).toBeVisible();
    expect(external).toEqual([]);
  });
test("image alpha, failed replacement and EXIF orientation remain usable", async ({
  page,
  browserName,
}) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await open(page);
  await page.getByRole("button", { name: "Image", exact: true }).click();
  await choose(page, "watermark-image", ["tests/fixtures/watermark/logo.png"]);
  await expect(page.locator(".watermark-image-input")).toContainText(
    "120 × 80",
  );
  await choose(page, "watermark-image", [
    "tests/fixtures/watermark/transparent.png",
  ]);
  await expect(page.getByRole("dialog")).toContainText("transparent");
  await page
    .getByRole("button", { name: "Back to editing", exact: true })
    .click();
  await expect(page.locator(".watermark-image-input")).toContainText(
    "120 × 80",
  );
  await page.getByRole("slider", { name: "Rotation", exact: true }).fill("0");
  await page.getByRole("slider", { name: "Opacity", exact: true }).fill("100");
  await page
    .getByRole("button", { name: "Add watermark →", exact: true })
    .click();
  await download(page, `${browserName}-image-alpha`);
  await selectTool(page, "Watermark PDF");
  await choose(page, "pdf-file", ["tests/fixtures/m8-device.pdf"]);
  await page.getByRole("button", { name: "Image", exact: true }).click();
  await choose(page, "watermark-image", [
    "tests/fixtures/watermark/orientation.jpg",
  ]);
  await expect(page.locator(".watermark-image-input")).toContainText(
    "60 × 100",
  );
  await page
    .getByRole("button", { name: "Add watermark →", exact: true })
    .click();
  await download(page, `${browserName}-image-orientation`);
});
test("repeat, invalid text/range recovery and leaving preserve current settings", async ({
  page,
  browserName,
}) => {
  await open(page);
  const text = page.getByRole("textbox", {
    name: "Watermark text",
    exact: true,
  });
  await text.fill("DRAFT 🙂");
  await expect(page.locator(".watermark-error")).toContainText(
    "does not support",
  );
  await expect(
    page.getByRole("button", { name: "Add watermark →", exact: true }),
  ).toBeDisabled();
  await text.fill("REVIEW");
  await page.getByRole("button", { name: "Repeat", exact: true }).click();
  await page.getByRole("slider", { name: "Size", exact: true }).fill("25");
  await page.getByRole("slider", { name: "Rotation", exact: true }).fill("0");
  await page.getByRole("radio", { name: "Page range", exact: true }).check();
  await page
    .getByRole("textbox", { name: "Page range", exact: true })
    .fill("0");
  await expect(page.locator(".watermark-error")).toContainText(
    "Choose positions",
  );
  await page
    .getByRole("textbox", { name: "Page range", exact: true })
    .fill("1");
  await selectTool(page, "PDF to JPG / PNG");
  await page.getByRole("button", { name: "Keep editing", exact: true }).click();
  await expect(text).toHaveValue("REVIEW");
  await expect(
    page.getByRole("button", { name: "Repeat", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page
    .getByRole("button", { name: "Add watermark →", exact: true })
    .click();
  await download(page, `${browserName}-repeat`);
});
test("cancellation and worker failure preserve settings and allow retry", async ({
  page,
  browserName,
}) => {
  await open(page);
  await page
    .getByRole("textbox", { name: "Watermark text", exact: true })
    .fill("KEEP DRAFT");
  await page.evaluate(() => {
    const w = window as unknown as { OriginalWorker: typeof Worker };
    w.OriginalWorker = Worker;
    window.Worker = class extends Worker {
      postMessage(message: unknown, ...args: unknown[]) {
        if ((message as { settings?: unknown }).settings) return;
        Reflect.apply(super.postMessage, this, [message, ...args]);
      }
    };
  });
  await page
    .getByRole("button", { name: "Add watermark →", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Cancel processing", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText("Cancelled");
  await page
    .getByRole("button", { name: "Back to editing", exact: true })
    .click();
  await expect(
    page.getByRole("textbox", { name: "Watermark text", exact: true }),
  ).toHaveValue("KEEP DRAFT");
  await page.evaluate(() => {
    const original = (window as unknown as { OriginalWorker: typeof Worker })
      .OriginalWorker;
    window.Worker = class extends original {
      postMessage(message: unknown, ...args: unknown[]) {
        if ((message as { settings?: unknown }).settings)
          throw Error("Synthetic worker failure");
        Reflect.apply(super.postMessage, this, [message, ...args]);
      }
    };
  });
  await page
    .getByRole("button", { name: "Add watermark →", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText("could not start");
  await page
    .getByRole("button", { name: "Back to editing", exact: true })
    .click();
  await page.evaluate(() => {
    window.Worker = (
      window as unknown as { OriginalWorker: typeof Worker }
    ).OriginalWorker;
  });
  await page
    .getByRole("button", { name: "Add watermark →", exact: true })
    .click();
  await download(page, `${browserName}-cancel-retry`);
});
for (const file of [
  "zero-pages",
  "encrypted",
  "corrupted",
  "large-50mb",
  "100mb",
])
  test(`safe refusal ${file} then working replacement`, async ({ page }) => {
    await page.goto("/watermark-pdf/");
    await page
      .locator("#pdf-file")
      .setInputFiles(`tests/fixtures/m5/${file}.pdf`);
    await expect(page.locator(".message")).toContainText(
      /couldn|unsupported|large|limit|encrypted|password|file|safely|no pages/i,
    );
    await expect(page.locator(".watermark-task,.delivery")).toHaveCount(0);
    await choose(page, "pdf-file", ["tests/fixtures/m8-device.pdf"]);
    await expect(
      page.getByRole("button", { name: "Add watermark →", exact: true }),
    ).toBeEnabled();
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
])
  test(`browser fixed regression ${fixture}`, async ({ page, browserName }) => {
    await open(page, `tests/fixtures/m5/${fixture}.pdf`);
    await page
      .getByRole("button", { name: "Add watermark →", exact: true })
      .click();
    const doc = await download(page, `${browserName}-${fixture}`);
    expect(doc.getPageCount()).toBe(
      fixture === "200-pages"
        ? 200
        : fixture === "100-pages"
          ? 100
          : ["mixed-page-size", "unusual-page-sizes"].includes(fixture)
            ? 3
            : 2,
    );
  });
test("ready watermark tab works offline with no document or font requests", async ({
  page,
  browserName,
  context,
}) => {
  await page.goto("/watermark-pdf/");
  await expect(page.locator(".status.ready")).toHaveCount(1);
  const requests: string[] = [];
  page.on("request", (r) => {
    if (/^https?:/.test(r.url())) requests.push(r.url());
  });
  await context.route(/^https?:/, (r) => r.abort("internetdisconnected"));
  if (browserName === "chromium") await context.setOffline(true);
  await choose(page, "pdf-file", ["tests/fixtures/m8-device.pdf"]);
  await page
    .getByRole("textbox", { name: "Watermark text", exact: true })
    .fill("离线审核");
  await page
    .getByRole("button", { name: "Add watermark →", exact: true })
    .click();
  await download(page, `${browserName}-offline`);
  expect(requests).toEqual([]);
});
