import { selectTool } from "./navigation";
import { test, expect, type Page } from "@playwright/test";
import { PDFDocument, PDFName, PDFDict } from "pdf-lib";
import { readFile, writeFile } from "node:fs/promises";
import {
  workerDiagnostics,
  reportWorkerDiagnostics,
} from "./worker-diagnostics";
const root = "tests/fixtures/m5/";
test.afterEach(async ({ page }, info) => {
  if (info.status !== info.expectedStatus) await reportWorkerDiagnostics(page);
});
async function start(page: Page, file = "normal-a4.pdf") {
  await page.goto("/");
  await selectTool(page, "Sign PDF");
  await page.locator("#pdf-file").setInputFiles(root + file);
  await expect(
    page.getByRole("button", { name: "Add signature", exact: true }),
  ).toBeEnabled();
  await expect(
    page.locator('.sign-sheet[data-current="true"] .sign-canvas canvas'),
  ).toBeVisible();
}
async function type(page: Page, name = "Alex Chen") {
  await page
    .getByRole("button", { name: "Add signature", exact: true })
    .click();
  await page.getByRole("tab", { name: "Type", exact: true }).click();
  const nameInput = page.getByRole("textbox", {
    name: "Your name",
    exact: true,
  });
  await nameInput.click();
  await nameInput.fill(name);
  await expect(nameInput).toHaveValue(name);
  await expect(page.locator(".sign-font-sample text").first()).toHaveCSS(
    "font-weight",
    "400",
  );
  await page
    .getByRole("button", { name: "Use signature", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Place at page center", exact: true })
    .click();
  await expect(page.locator(".sign-placement")).toHaveCount(1);
}
test("Sign asks before removing standard claims and opens the confirmed copy", async ({
  page,
}) => {
  await page.goto("/");
  await selectTool(page, "Sign PDF");
  await expect(page.locator("#pdf-file")).toBeEnabled({ timeout: 30000 });
  await page
    .locator("#pdf-file")
    .setInputFiles("tests/fixtures/split/ordinary.pdf");
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "Create an ordinary PDF copy",
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByRole("button", {
      name: "Create ordinary copy without standard claims",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("button", { name: "Add signature", exact: true }),
  ).toBeEnabled();
  await expect(
    page.locator('.sign-sheet[data-current="true"] .sign-canvas canvas'),
  ).toBeVisible();
  await type(page);
  await page
    .getByRole("button", { name: "Create signed PDF", exact: true })
    .click();
  await expect(page.locator(".delivery")).toBeVisible({ timeout: 30000 });
});

test("Type: offline multilingual signing, sizes, undo and download end the task", async ({
  page,
  context,
}, info) => {
  const external: string[] = [];
  page.on("request", (r) => {
    if (
      !r.url().startsWith(String(info.project.use.baseURL) + "/") &&
      !r.url().startsWith("blob:") &&
      !r.url().startsWith("data:")
    )
      external.push(r.url());
  });
  await start(page);
  // Load the selected typed style online before testing its offline reuse.
  await page
    .getByRole("button", { name: "Add signature", exact: true })
    .click();
  await page.getByRole("tab", { name: "Type", exact: true }).click();
  await page
    .getByRole("textbox", { name: "Your name", exact: true })
    .fill("王小明 Alex");
  await expect(
    page.getByRole("button", { name: "Use signature", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("dialog", { name: "Create signature" })
    .getByRole("button", { name: "Cancel", exact: true })
    .click();
  // Windows WebKit global offline also blocks local blob: images/workers.
  // Reject every HTTP(S) request instead; Chromium additionally uses native offline.
  await context.route(/^https?:/, (route) =>
    route.abort("internetdisconnected"),
  );
  if (info.project.name === "chromium") await context.setOffline(true);
  await type(page, "王小明 Alex");
  await page.getByRole("button", { name: "Size", exact: true }).click();
  await page
    .getByRole("button", { name: "Larger signature", exact: true })
    .click();
  await page.getByRole("button", { name: "Done", exact: true }).click();
  await page.getByRole("button", { name: "Move", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Create signed PDF", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Cancel placement", exact: true })
    .click();
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(page.locator(".sign-placement")).toHaveCount(0);
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(page.locator(".sign-placement")).toHaveCount(1);
  await page
    .getByRole("button", { name: "Create signed PDF", exact: true })
    .click();
  await expect(page.locator(".delivery")).toBeVisible({ timeout: 30000 });
  const event = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PDF", exact: true }).click();
  const dl = await event;
  const path = info.outputPath("typed-signed.pdf");
  await dl.saveAs(path);
  expect((await PDFDocument.load(await readFile(path))).getPageCount()).toBe(2);
  expect(external).toEqual([]);
  await context.setOffline(false);
  await context.unroute(/^https?:/);
  await selectTool(page, "Split a PDF");
  await expect(page.locator("#pdf-file")).toBeEnabled();
  await expect(page.locator(".sign-task")).toHaveCount(0);
});
test("Draw: clear/undo, placement, keyboard move and pending-add cancel", async ({
  page,
}) => {
  await start(page, "mixed-page-size.pdf");
  await page
    .getByRole("button", { name: "Add signature", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Use signature", exact: true }),
  ).toBeDisabled();
  const b = (await page.locator(".signature-draw").boundingBox())!;
  await page.mouse.move(b.x + 30, b.y + 40);
  await page.mouse.down();
  await page.mouse.move(b.x + b.width * 0.6, b.y + b.height * 0.7, {
    steps: 12,
  });
  await page.mouse.up();
  await page.getByRole("button", { name: "Clear", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Use signature", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Undo stroke", exact: true }).click();
  await page
    .getByRole("button", { name: "Use signature", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Place at page center", exact: true })
    .click();
  const el = page.locator(".sign-placement");
  await el.focus();
  const before = await el.getAttribute("style");
  await page.keyboard.press("ArrowRight");
  expect(await el.getAttribute("style")).not.toBe(before);
  await page.getByRole("button", { name: "Add another", exact: true }).click();
  await page
    .getByRole("button", { name: "Cancel placement", exact: true })
    .click();
  await expect(el).toHaveCount(1);
  await page
    .getByRole("button", { name: "Create signed PDF", exact: true })
    .click();
  await expect(page.locator(".delivery")).toBeVisible();
});
test("Image and phone task guards preserve drafts, finished navigation resets input", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await start(page);
  await page
    .getByRole("button", { name: "Add signature", exact: true })
    .click();
  await page.getByRole("tab", { name: "Image", exact: true }).click();
  await page
    .getByLabel("Choose signature image")
    .setInputFiles(root + "signature.png");
  await page
    .getByRole("button", { name: "Use signature", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Place at page center", exact: true })
    .click();
  await page.getByRole("button", { name: "← All tools", exact: true }).click();
  await expect(
    page.getByRole("dialog", { name: "Leave this task?" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Keep editing", exact: true }).click();
  await expect(page.locator(".sign-placement")).toHaveCount(1);
  await page
    .getByRole("button", { name: "Create signed PDF", exact: true })
    .click();
  await expect(page.locator(".delivery")).toBeVisible();
});
for (const file of [
  "encrypted.pdf",
  "corrupted.pdf",
  "zero-pages.pdf",
  "large-50mb.pdf",
  "100mb.pdf",
])
  test(`edge input safely refused: ${file}`, async ({ page }) => {
    await page.goto("/");
    await selectTool(page, "Sign PDF");
    await page.locator("#pdf-file").setInputFiles(root + file);
    await expect(page.locator("#pdf-file")).toBeEnabled({ timeout: 30000 });
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page.locator(".delivery")).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Create signed PDF", exact: true }),
    ).toHaveCount(0);
    await page.locator("#pdf-file").setInputFiles(root + "normal-a4.pdf");
    await expect(
      page.getByRole("button", { name: "Add signature", exact: true }),
    ).toBeEnabled();
  });
test("200 pages and unusual sizes retain signature positions across page and zoom changes", async ({
  page,
}) => {
  await start(page, "200-pages.pdf");
  await type(page);
  await page.getByLabel("Signature page").fill("200");
  await expect(
    page.locator('.sign-sheet[data-current="true"] .sign-canvas canvas'),
  ).toBeVisible();
  await expect(page.locator(".sign-placement")).toHaveCount(0);
  await page.getByRole("button", { name: "Add another", exact: true }).click();
  await page
    .getByRole("button", { name: "Place at page center", exact: true })
    .click();
  await page.getByLabel("Signature zoom", { exact: true }).selectOption("1.5");
  await expect(page.locator(".sign-placement")).toHaveCount(1);
  await page
    .getByRole("button", { name: "Create signed PDF", exact: true })
    .click();
  await expect(page.locator(".delivery")).toBeVisible({ timeout: 30000 });
});

test("Type drafts, missing glyphs, precise size recovery and page picker", async ({
  page,
}, info) => {
  await start(page, "unusual-page-sizes.pdf");
  await page.getByRole("button", { name: "Pages", exact: true }).click();
  await page
    .getByRole("dialog", { name: "Choose a page" })
    .getByRole("button", { name: "Page 3", exact: true })
    .click();
  await expect(page.getByLabel("Signature page")).toHaveValue("3");
  await page
    .getByRole("button", { name: "Add signature", exact: true })
    .click();
  await page.getByRole("tab", { name: "Type", exact: true }).click();
  await page
    .getByRole("textbox", { name: "Your name", exact: true })
    .fill("😀");
  await expect(
    page.getByRole("button", { name: "Use signature", exact: true }),
  ).toBeDisabled();
  const longName = "A".repeat(121);
  await page
    .getByRole("textbox", { name: "Your name", exact: true })
    .fill(longName);
  await expect(
    page.getByRole("textbox", { name: "Your name", exact: true }),
  ).toHaveValue(longName);
  await expect(page.getByRole("alert")).toContainText("has not been shortened");
  await expect(
    page.getByRole("button", { name: "Use signature", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("textbox", { name: "Your name", exact: true })
    .fill("Alexandra Chen");
  await page.getByRole("tab", { name: "Draw", exact: true }).click();
  await page.getByRole("tab", { name: "Type", exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: "Your name", exact: true }),
  ).toHaveValue("Alexandra Chen");
  await page.screenshot({
    path: info.outputPath("type-styles.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Use signature", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Place at page center", exact: true })
    .click();
  await page.getByRole("button", { name: "Size", exact: true }).click();
  await page.getByText("Precise position & size", { exact: true }).click();
  const width = page.getByRole("spinbutton", {
    name: "Width (mm)",
    exact: true,
  });
  await width.fill("");
  await expect(
    page.getByRole("button", { name: "Done", exact: true }),
  ).toBeDisabled();
  await width.fill("30");
  await expect(
    page.getByRole("button", { name: "Done", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Done", exact: true }).click();
  for (const w of [320, 390, 768, 1280]) {
    await page.setViewportSize({ width: w, height: 844 });
    await expect(page.locator(".sign-placement")).toBeVisible();
    await expect(page.locator(".sign-placement")).toBeInViewport();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBe(true);
    await page
      .getByRole("button", { name: "Create signed PDF", exact: true })
      .scrollIntoViewIfNeeded();
    await page.screenshot({
      path: info.outputPath(`sign-workspace-${w}.png`),
      fullPage: true,
    });
  }
});

test("signature image validation and offline import recover without losing the task", async ({
  page,
  context,
}, info) => {
  await start(page);
  await context.route(/^https?:/, (route) =>
    route.abort("internetdisconnected"),
  );
  if (info.project.name === "chromium") await context.setOffline(true);
  await page
    .getByRole("button", { name: "Add signature", exact: true })
    .click();
  await page.getByRole("tab", { name: "Image", exact: true }).click();
  const input = page.getByLabel("Choose signature image");
  for (const size of [4, 2050]) {
    const png = await page.evaluate((n) => {
      const c = document.createElement("canvas");
      c.width = c.height = n;
      return c.toDataURL("image/png").split(",")[1]!;
    }, size);
    await input.setInputFiles({
      name: "synthetic.png",
      mimeType: "image/png",
      buffer: Buffer.from(png, "base64"),
    });
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Use signature", exact: true }),
    ).toBeDisabled();
  }
  for (const buffer of [
    Buffer.from("corrupt"),
    Buffer.alloc(5 * 1024 * 1024 + 1),
  ]) {
    await input.setInputFiles({
      name: "synthetic.jpg",
      mimeType: "image/jpeg",
      buffer,
    });
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Use signature", exact: true }),
    ).toBeDisabled();
  }
  await input.setInputFiles(root + "signature.png");
  await page
    .getByRole("button", { name: "Use signature", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Place at page center", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Create signed PDF", exact: true })
    .click();
  await expect(page.locator(".delivery")).toBeVisible();
});

test("generation cancellation and worker failure preserve the draft and allow retry", async ({
  page,
}) => {
  await start(page);
  await type(page);
  await page.evaluate(() => {
    const Native = window.Worker;
    let count = 0;
    window.Worker = class extends Native {
      constructor(url: string | URL, options?: WorkerOptions) {
        super(url, options);
        count++;
        if (count === 1) this.postMessage = () => {};
        else if (count === 2)
          this.postMessage = () =>
            queueMicrotask(() =>
              this.dispatchEvent(
                new ErrorEvent("error", {
                  message: "Synthetic worker failure",
                  cancelable: true,
                }),
              ),
            );
      }
    };
  });
  await page
    .getByRole("button", { name: "Create signed PDF", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Cancel processing", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator(".sign-placement")).toHaveCount(1);
  await page
    .getByRole("button", { name: "Create signed PDF", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("draft is unchanged");
  await expect(page.locator(".sign-placement")).toHaveCount(1);
  await page
    .getByRole("button", { name: "Create signed PDF", exact: true })
    .click();
  await expect(page.locator(".delivery")).toBeVisible();
});

test("form overlap is explained and moving the signature allows safe retry", async ({
  page,
}) => {
  await start(page, "form.pdf");
  await type(page);
  await page.getByRole("button", { name: "Size", exact: true }).click();
  await page.getByText("Precise position & size", { exact: true }).click();
  await page
    .getByRole("spinbutton", { name: "X from left (mm)", exact: true })
    .fill("14");
  await page
    .getByRole("spinbutton", { name: "Y from top (mm)", exact: true })
    .fill("36");
  await page.getByRole("button", { name: "Done", exact: true }).click();
  await page
    .getByRole("button", { name: "Create signed PDF", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "overlaps a form field or annotation",
  );
  await expect(page.getByRole("alert")).toBeInViewport();
  await expect(page.locator(".sign-placement")).toHaveCount(1);
  await page.getByRole("button", { name: "Move", exact: true }).click();
  await page
    .getByRole("button", { name: "Place at page center", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Create signed PDF", exact: true })
    .click();
  await expect(page.locator(".delivery")).toBeVisible();
});

test("DPR 2 zoom and viewport changes retain document-relative placement", async ({
  browser,
}, info) => {
  const ctx = await browser.newContext({
    baseURL: String(info.project.use.baseURL),
    viewport: { width: 900, height: 900 },
    deviceScaleFactor: 2,
    hasTouch: true,
  });
  try {
    const page = await ctx.newPage();
    await start(page);
    await type(page);
    const bounds = () =>
      page.locator(".sign-placement").evaluate((el) => {
        const a = el.getBoundingClientRect(),
          b = el.parentElement!.getBoundingClientRect();
        return [
          (a.x - b.x) / b.width,
          (a.y - b.y) / b.height,
          a.width / b.width,
          a.height / b.height,
        ];
      });
    const before = await bounds();
    await page.getByLabel("Signature zoom", { exact: true }).selectOption("2");
    await expect(
      page.locator('.sign-sheet[data-current="true"] .sign-canvas canvas'),
    ).toBeVisible();
    const after = await bounds();
    before.forEach((v, i) => expect(after[i]).toBeCloseTo(v, 3));
    await page.setViewportSize({ width: 900, height: 500 });
    await expect(
      page.locator('.sign-sheet[data-current="true"] .sign-canvas canvas'),
    ).toBeVisible();
    const landscape = await bounds();
    before.forEach((v, i) => expect(landscape[i]).toBeCloseTo(v, 3));
    await page
      .getByRole("button", { name: "Create signed PDF", exact: true })
      .click();
    await expect(page.locator(".delivery")).toBeVisible();
  } finally {
    await ctx.close();
  }
});

test("PERF-SIGN ordinary PDF: two warmups and 20 end-to-end generation measurements", async ({
  page,
}, info) => {
  test.setTimeout(240000);
  await workerDiagnostics(page);
  await start(page);
  const measurements: number[] = [];
  for (let i = 0; i < 22; i++) {
    if (i) {
      await page
        .getByRole("button", { name: "Choose new files", exact: true })
        .click();
      await page.locator("#pdf-file").setInputFiles(root + "normal-a4.pdf");
      await expect(
        page.getByRole("button", { name: "Add signature", exact: true }),
      ).toBeEnabled();
    }
    await type(page);
    const began = Date.now();
    await page
      .getByRole("button", { name: "Create signed PDF", exact: true })
      .click();
    await expect(page.locator(".delivery")).toBeVisible({ timeout: 30000 });
    if (i >= 2) measurements.push(Date.now() - began);
  }
  const sorted = [...measurements].sort((a, b) => a - b),
    p95 = sorted[Math.ceil(0.95 * sorted.length) - 1]!;
  await writeFile(
    info.outputPath("sign-performance.json"),
    JSON.stringify(
      {
        engine: info.project.name,
        warmups: 2,
        measurements,
        p95,
        thresholdMs: 5000,
        note: "Desktop browser synthetic 2-page PDF; not iPhone performance",
      },
      null,
      2,
    ),
  );
  expect(p95).toBeLessThanOrEqual(5000);
});
for (const width of [1280, 390])
  test(`continuous sign reading at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 900 });
    await start(page, "100-pages.pdf");
    const view = page.locator(".sign-viewport"),
      input = page.getByLabel("Signature page");
    const first = page.locator('.sign-sheet[data-page="1"]');
    await expect(
      page.getByLabel("Signature zoom", { exact: true }),
    ).toHaveValue("1");
    const before = await first.boundingBox();
    await view.hover();
    await page.mouse.wheel(0, 120);
    await expect
      .poll(() => view.evaluate((el) => el.scrollTop))
      .toBeGreaterThan(40);
    const after = await first.boundingBox();
    expect(before!.y - after!.y).toBeGreaterThan(40);
    await expect(input).toHaveValue("1");
    // A page boundary leaves both pages in the same scrollable document.
    await view.evaluate((el) => {
      const s = el.querySelector<HTMLElement>('[data-page="2"]')!;
      el.scrollTop = s.offsetTop - (el as HTMLElement).offsetTop - 150;
    });
    await expect(page.locator('.sign-sheet[data-page="2"]')).toBeInViewport();
    const canvases = await view.locator("canvas").count();
    expect(canvases).toBeLessThanOrEqual(5);
    await page
      .getByRole("button", { name: "Add signature", exact: true })
      .click();
    await page.getByRole("tab", { name: "Type", exact: true }).click();
    await page
      .getByRole("textbox", { name: "Your name", exact: true })
      .fill("Reader Test");
    await page
      .getByRole("button", { name: "Use signature", exact: true })
      .click();
    await input.fill("6");
    const sixth = page.locator('.sign-sheet[data-page="6"] .sign-paper');
    await expect(sixth.locator("canvas")).toBeVisible();
    await sixth.dispatchEvent("pointerdown", {
      pointerType: "touch",
      pointerId: 1,
      clientX: 60,
      clientY: 80,
    });
    await view.evaluate((el) => {
      el.scrollTop += 70;
    });
    await sixth.dispatchEvent("pointerup", {
      pointerType: "touch",
      pointerId: 1,
      clientX: 60,
      clientY: 80,
    });
    await expect(sixth.locator(".sign-placement")).toHaveCount(0);
    await input.fill("6");
    await sixth.click({ position: { x: 60, y: 80 } });
    await expect(sixth.locator(".sign-placement")).toHaveCount(1);
    await page
      .getByRole("button", { name: "Add another", exact: true })
      .click();
    await input.fill("2");
    const second = page.locator('.sign-sheet[data-page="2"] .sign-paper');
    await expect(second.locator("canvas")).toBeVisible();
    await second.click({ position: { x: 60, y: 80 } });
    await expect(second.locator(".sign-placement")).toHaveCount(1);
    await input.fill("80");
    await expect(
      page.locator('.sign-sheet[data-page="80"] canvas'),
    ).toBeVisible();
    await page
      .getByLabel("Signature zoom", { exact: true })
      .selectOption("1.5");
    await expect(input).toHaveValue("80");
    await expect
      .poll(() => view.locator("canvas").count())
      .toBeLessThanOrEqual(5);
    await expect
      .poll(() =>
        view
          .locator("canvas")
          .evaluateAll((nodes) =>
            nodes.reduce(
              (n, c) =>
                n +
                (c as HTMLCanvasElement).width *
                  (c as HTMLCanvasElement).height,
              0,
            ),
          ),
      )
      .toBeLessThanOrEqual(9_000_000);
    await input.fill("6");
    await expect(sixth.locator(".sign-placement")).toHaveCount(1);
    await input.fill("100");
    await expect(
      page.getByRole("button", { name: "Next page", exact: true }),
    ).toBeDisabled();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      ),
    ).toBe(false);
    await page.screenshot({ path: info.outputPath("continuous-reading.png") });
    await page
      .getByRole("button", { name: "Create signed PDF", exact: true })
      .click();
    await expect(page.locator(".delivery")).toBeVisible({ timeout: 60000 });
    const download = page.waitForEvent("download");
    await page
      .getByRole("button", { name: "Download PDF", exact: true })
      .click();
    const output = info.outputPath("continuous-signed.pdf");
    await (await download).saveAs(output);
    const pdf = await PDFDocument.load(await readFile(output));
    expect(pdf.getPageCount()).toBe(100);
    const stamped = pdf.getPages().flatMap((p, i) => {
      const images = p.node
        .Resources()
        ?.lookupMaybe(PDFName.of("XObject"), PDFDict);
      return images?.keys().length ? [i + 1] : [];
    });
    expect(stamped).toEqual([2, 6]);
  });

test("sign preview stays stable with classic scrollbars", async ({ page }) => {
  await start(page);
  await page.addStyleTag({
    content: ".sign-viewport::-webkit-scrollbar{width:17px;height:17px}",
  });
  await page
    .locator('.sign-sheet[data-current="true"] .sign-canvas')
    .evaluate((el) => {
      el.setAttribute("data-blank-frames", "0");
      new MutationObserver((records) => {
        for (const record of records) {
          if (record.removedNodes.length && !record.addedNodes.length)
            el.setAttribute(
              "data-blank-frames",
              String(Number(el.getAttribute("data-blank-frames")) + 1),
            );
        }
      }).observe(el, { childList: true });
    });
  await page
    .getByRole("combobox", { name: "Signature zoom" })
    .selectOption("1.5");
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 720 });
    await page.waitForTimeout(700);
    const replacements = await page
      .locator('.sign-sheet[data-current="true"] .sign-canvas')
      .evaluate(
        (el) =>
          new Promise<number>((resolve) => {
            let count = 0;
            const observer = new MutationObserver((records) => {
              count += records.length;
            });
            observer.observe(el, { childList: true });
            setTimeout(() => {
              observer.disconnect();
              resolve(count);
            }, 1800);
          }),
      );
    expect(replacements, `idle redraws at ${width}px`).toBe(0);
    await expect(
      page.locator('.sign-sheet[data-current="true"] .sign-canvas canvas'),
    ).toBeVisible();
  }
  await expect(
    page.locator('.sign-sheet[data-current="true"] .sign-canvas'),
  ).toHaveAttribute("data-blank-frames", "0");
});
