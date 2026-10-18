import { test, expect, type Page } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";
import { PDFDocument } from "pdf-lib";
import { selectToolPath } from "./navigation";
const fixture = "tests/fixtures/m5/";
test.afterEach(async ({ page }, info) => {
  if (info.status === info.expectedStatus) return;
  const state = await page
    .evaluate(() => {
      const view = document.querySelector<HTMLElement>(
        ".numbers-task .watermark-viewport",
      );
      return {
        width: innerWidth,
        height: innerHeight,
        outerScroll: scrollY,
        input: document.querySelector<HTMLInputElement>(
          'input[aria-label="Preview page"]',
        )?.value,
        viewport: view && {
          top: view.scrollTop,
          height: view.clientHeight,
          scrollHeight: view.scrollHeight,
          bounds: view.getBoundingClientRect().toJSON(),
        },
        pages: [1, 150, 151].map((n) => {
          const e = document.querySelector(`.number-sheet[data-page="${n}"]`);
          return { page: n, bounds: e?.getBoundingClientRect().toJSON() };
        }),
      };
    })
    .catch(() => ({ unavailable: true }));
  await writeFile(
    info.outputPath("synthetic-preview-layout.json"),
    JSON.stringify(state, null, 2),
  );
  await page
    .screenshot({
      path: info.outputPath("synthetic-failed-preview.png"),
      fullPage: true,
    })
    .catch(() => {});
});
async function open(page: Page, name = "normal-a4.pdf") {
  await page.goto("/add-page-numbers/");
  await page.locator("#pdf-file").setInputFiles(fixture + name);
  await expect(
    page.getByRole("button", { name: "Add page numbers →", exact: true }),
  ).toBeEnabled();
  await expect(
    page.locator('.number-sheet[data-page="1"] canvas'),
  ).toBeVisible();
}
async function generate(page: Page) {
  await page
    .getByRole("button", { name: "Add page numbers →", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Your numbered PDF is ready",
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.locator(".numbers-task,.number-actions")).toHaveCount(0);
}
test("defaults produce a downloadable numbered PDF and end the task cleanly", async ({
  page,
}) => {
  await open(page);
  await expect(
    page.getByRole("button", { name: "Bottom center", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await generate(page);
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PDF", exact: true }).click();
  const path = await (await pending).path();
  expect((await PDFDocument.load(await readFile(path!))).getPageCount()).toBe(
    2,
  );
  await page
    .getByRole("button", { name: "Choose new files", exact: true })
    .click();
  await expect(page.locator("#pdf-file")).toHaveValue("");
  const chooser = page.waitForEvent("filechooser");
  await page.locator("#pdf-file").click();
  await (await chooser).setFiles([]);
  await expect(page.getByRole("dialog")).toHaveCount(0);
});
test("cover and range numbering use one plan in preview and downloaded output", async ({
  page,
}, info) => {
  await page.goto("/add-page-numbers/");
  await page
    .locator("#pdf-file")
    .setInputFiles("docs/ux/public-synthetic-only/demo-a.pdf");
  await expect(
    page.getByRole("button", { name: "Add page numbers →", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("combobox", { name: "Number format", exact: true })
    .selectOption("fraction");
  await page
    .getByRole("radio", { name: "Skip first page", exact: true })
    .check();
  await expect(
    page.locator('.number-sheet[data-page="1"] .watermark-page-label'),
  ).toContainText("No added number");
  await page.getByRole("button", { name: "Next page", exact: true }).click();
  await expect(
    page.locator('.number-sheet[data-page="2"] .watermark-page-label'),
  ).toContainText("1 / 5");
  await page.getByRole("radio", { name: "Page range", exact: true }).check();
  await page.getByLabel("From PDF page", { exact: true }).fill("2");
  await page.getByLabel("To PDF page", { exact: true }).fill("6");
  await page.getByLabel("Start number", { exact: true }).fill("3");
  await expect(page.locator(".number-summary")).toContainText("Numbers 3–7");
  await expect(
    page.locator('.number-sheet[data-page="2"] .watermark-page-label'),
  ).toContainText("3 / 7");
  await generate(page);
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PDF", exact: true }).click();
  const bytes = await readFile((await (await pending).path())!);
  await writeFile(info.outputPath("numbered-range.pdf"), bytes);
  expect((await PDFDocument.load(bytes)).getPageCount()).toBe(6);
});
test("invalid ranges, empty fields, single cover and too-small pages never generate stale results", async ({
  page,
}) => {
  await open(page);
  const action = page.getByRole("button", {
    name: "Add page numbers →",
    exact: true,
  });
  for (const value of ["", "0", "999999", "1.5"]) {
    await page.getByLabel("Start number", { exact: true }).fill(value);
    await expect(action).toBeDisabled();
    await expect(page.getByRole("alert")).toBeVisible();
  }
  await page.getByLabel("Start number", { exact: true }).fill("1");
  await page.getByRole("radio", { name: "Page range", exact: true }).check();
  await page.getByLabel("From PDF page", { exact: true }).fill("2");
  await page.getByLabel("To PDF page", { exact: true }).fill("1");
  await expect(action).toBeDisabled();
  await page.getByLabel("To PDF page", { exact: true }).fill("2");
  await expect(action).toBeEnabled();
  await page.goto("/add-page-numbers/");
  const single = await PDFDocument.create();
  single.addPage([300, 400]);
  await page.locator("#pdf-file").setInputFiles({
    name: "single.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from(await single.save()),
  });
  await expect(action).toBeEnabled();
  await page
    .getByRole("radio", { name: "Skip first page", exact: true })
    .check();
  await expect(action).toBeDisabled();
  await expect(page.locator(".delivery")).toHaveCount(0);
  await page.goto("/add-page-numbers/");
  const tiny = await PDFDocument.create();
  tiny.addPage([20, 20]);
  await page.locator("#pdf-file").setInputFiles({
    name: "tiny.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from(await tiny.save()),
  });
  await expect(page.locator(".numbers-task").getByRole("alert")).toContainText(
    /fit|small/i,
  );
  await expect(action).toBeDisabled();
});
test("continuous preview navigation, six positions and appearance stay usable on phone and desktop", async ({
  page,
}, info) => {
  await open(page, "200-pages.pdf");
  for (const width of [1280, 390, 320, 844]) {
    await page.setViewportSize({ width, height: width === 844 ? 390 : 900 });
    await page.getByLabel("Preview page", { exact: true }).fill("150");
    await page.getByLabel("Preview page", { exact: true }).press("Enter");
    await expect(page.getByLabel("Preview page", { exact: true })).toHaveValue(
      "150",
    );
    await expect(
      page.locator('.number-sheet[data-page="150"]'),
    ).toBeInViewport();
    await page.getByRole("button", { name: "Next page", exact: true }).click();
    await expect(page.getByLabel("Preview page", { exact: true })).toHaveValue(
      "151",
    );
    await expect(
      page.locator('.number-sheet[data-page="151"]'),
    ).toBeInViewport();
    for (const label of [
      "Top left",
      "Top center",
      "Top right",
      "Bottom left",
      "Bottom center",
      "Bottom right",
    ]) {
      await page.getByRole("button", { name: label, exact: true }).click();
      await expect(
        page.getByRole("button", { name: label, exact: true }),
      ).toHaveAttribute("aria-pressed", "true");
    }
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    expect(
      await page.locator(".numbers-task canvas").count(),
    ).toBeLessThanOrEqual(5);
    await page
      .getByRole("button", { name: "Add page numbers →", exact: true })
      .scrollIntoViewIfNeeded();
    await expect(
      page.getByRole("button", { name: "Add page numbers →", exact: true }),
    ).toBeInViewport();
    await page.screenshot({
      path: info.outputPath(`numbers-${width}.png`),
      fullPage: true,
    });
  }
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.getByLabel("Preview page", { exact: true }).fill("150");
  await page.getByLabel("Preview page", { exact: true }).press("Enter");
  const viewport = page.locator(".numbers-task .watermark-viewport");
  await viewport.hover();
  await page.mouse.wheel(0, 900);
  await expect(
    page.getByLabel("Preview page", { exact: true }),
  ).not.toHaveValue("150");
});
test("settings do not replace an idle page canvas and preview size matches the physical numbering plan", async ({
  page,
}) => {
  await open(page, "mixed-page-size.pdf");
  await expect(
    page.locator('.number-sheet[data-page="1"] .number-overlay'),
  ).toBeVisible();
  const original = await page
    .locator('.number-sheet[data-page="1"] canvas')
    .elementHandle();
  await page.getByText("Appearance", { exact: true }).click();
  await page.getByLabel("Font size (pt)", { exact: true }).fill("18");
  await page.getByLabel("Margin (mm)", { exact: true }).fill("15");
  await page.waitForTimeout(300);
  expect(await original!.evaluate((e) => e.isConnected)).toBe(true);
  const placement = await page
    .locator('.number-sheet[data-page="1"]')
    .evaluate((e) => {
      const p = e.getBoundingClientRect(),
        r = e.querySelector("img.number-overlay")!.getBoundingClientRect();
      return {
        bottom: (p.bottom - r.bottom) / p.height,
        center: (r.left + r.width / 2 - p.left) / p.width,
      };
    });
  expect(placement.center).toBeCloseTo(0.5, 2);
  expect(placement.bottom).toBeGreaterThan(0.03);
});
test("dirty-task leave, cancel processing and worker failure keep their original settings", async ({
  page,
}) => {
  await open(page);
  await page.getByLabel("Start number", { exact: true }).fill("12");
  await page.getByRole("button", { name: "← All tools", exact: true }).click();
  await page.getByRole("button", { name: "Keep editing", exact: true }).click();
  await expect(page.getByLabel("Start number", { exact: true })).toHaveValue(
    "12",
  );
  await page.evaluate(() => {
    const send = Worker.prototype.postMessage;
    Reflect.set(window, "numberTestSend", send);
    Worker.prototype.postMessage = function (this: Worker, data, ...args) {
      if (data?.settings?.format) return;
      return Reflect.apply(send, this, [data, ...args]);
    } as typeof send;
  });
  await page
    .getByRole("button", { name: "Add page numbers →", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Cancel processing", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Back to editing", exact: true })
    .click();
  await expect(page.getByLabel("Start number", { exact: true })).toHaveValue(
    "12",
  );
  await expect(page.locator(".delivery")).toHaveCount(0);
  await page.evaluate(() => {
    const send = Reflect.get(window, "numberTestSend") as Worker["postMessage"];
    Worker.prototype.postMessage = function (this: Worker, data, ...args) {
      if (data?.settings?.format)
        throw Error("Synthetic page number worker failure");
      return Reflect.apply(send, this, [data, ...args]);
    } as typeof send;
  });
  await page
    .getByRole("button", { name: "Add page numbers →", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "PDF needs attention", exact: true }),
  ).toContainText("Numbering could not start");
  await page
    .getByRole("button", { name: "Back to editing", exact: true })
    .click();
  await expect(page.getByLabel("Start number", { exact: true })).toHaveValue(
    "12",
  );
  await page.evaluate(() => {
    Worker.prototype.postMessage = Reflect.get(
      window,
      "numberTestSend",
    ) as Worker["postMessage"];
  });
  await generate(page);
});
for (const file of [
  "zero-pages.pdf",
  "corrupted.pdf",
  "encrypted.pdf",
  "large-50mb.pdf",
  "100mb.pdf",
])
  test(`safe refusal and replacement picker: ${file}`, async ({ page }) => {
    await page.goto("/add-page-numbers/");
    await page.locator("#pdf-file").setInputFiles(fixture + file);
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page.locator(".numbers-task")).toHaveCount(0);
    await page.locator("#pdf-file").setInputFiles(fixture + "normal-a4.pdf");
    await expect(
      page.getByRole("button", { name: "Add page numbers →", exact: true }),
    ).toBeEnabled();
  });
test("a ready tool works with all HTTP requests blocked", async ({
  page,
  context,
}) => {
  await page.goto("/add-page-numbers/");
  await expect(page.locator(".status.ready")).toBeAttached();
  const requests: string[] = [];
  await context.route(/^https?:/, (route) => {
    requests.push(route.request().url());
    return route.abort("internetdisconnected");
  });
  await page.locator("#pdf-file").setInputFiles(fixture + "normal-a4.pdf");
  await expect(
    page.getByRole("button", { name: "Add page numbers →", exact: true }),
  ).toBeEnabled();
  await generate(page);
  expect(requests).toEqual([]);
});
test("completed numbering to other tools starts an empty responsive picker", async ({
  page,
}) => {
  for (const target of ["add-page-numbers", "split-pdf", "merge-pdf"]) {
    await open(page);
    await generate(page);
    await selectToolPath(page, target);
    const id = target === "merge-pdf" ? "combine-files" : "pdf-file";
    await expect(page.locator("#" + id)).toHaveValue("");
    const pending = page.waitForEvent("filechooser");
    await page.locator("#" + id).click();
    await (await pending).setFiles([]);
    await expect(page.locator("[inert],dialog[open]")).toHaveCount(0);
  }
});

test("font loading failure retains an early selected file and retries without reselection", async ({
  page,
}) => {
  let allow = false;
  await page.route("**/number-fonts/*.ttf", (route) =>
    allow ? route.continue() : route.abort("failed"),
  );
  await page.goto("/add-page-numbers/");
  await page.locator("#pdf-file").setInputFiles(fixture + "normal-a4.pdf");
  await expect(
    page.getByRole("button", { name: "Retry loading", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".delivery")).toHaveCount(0);
  allow = true;
  await page
    .getByRole("button", { name: "Retry loading", exact: true })
    .click();
  await expect(page.locator(".watermark-filename")).toHaveText("normal-a4.pdf");
  await expect(
    page.getByRole("button", { name: "Add page numbers →", exact: true }),
  ).toBeEnabled();
  await generate(page);
});

test("a corrupt successful font response is not cached across retry", async ({
  page,
}) => {
  let allow = false;
  await page.route("**/number-fonts/*.ttf", (route) =>
    allow
      ? route.continue()
      : route.fulfill({
          status: 200,
          contentType: "font/ttf",
          body: "synthetic damaged font",
        }),
  );
  await page.goto("/add-page-numbers/");
  await page.locator("#pdf-file").setInputFiles(fixture + "normal-a4.pdf");
  const retry = page.getByRole("button", {
    name: "Retry loading",
    exact: true,
  });
  await expect(retry).toBeVisible();
  allow = true;
  await retry.click();
  await expect(
    page.getByRole("button", { name: "Add page numbers →", exact: true }),
  ).toBeEnabled();
  await generate(page);
});

for (const kind of ["ordinary", "credentials"] as const) {
  test(`${kind} copy consent stays within numbering until output is created`, async ({
    page,
  }) => {
    await page.goto("/add-page-numbers/");
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
    await expect(page.locator(".delivery")).toHaveCount(0);
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
      page.getByRole("button", { name: "Add page numbers →", exact: true }),
    ).toBeEnabled();
    await expect(page.locator(".delivery")).toHaveCount(0);
    await generate(page);
  });
}

test("twenty normal generations after warmup meet the desktop latency budget", async ({
  page,
}, info) => {
  const times: number[] = [];
  await open(page);
  for (let n = 0; n < 22; n++) {
    const started = performance.now();
    await generate(page);
    if (n >= 2) times.push(performance.now() - started);
    if (n < 21) {
      await page
        .getByRole("button", { name: "Choose new files", exact: true })
        .click();
      await page.locator("#pdf-file").setInputFiles(fixture + "normal-a4.pdf");
      await expect(
        page.getByRole("button", { name: "Add page numbers →", exact: true }),
      ).toBeEnabled();
    }
  }
  const sorted = [...times].sort((a, b) => a - b),
    p95 = sorted[Math.ceil(sorted.length * 0.95) - 1]!;
  await writeFile(
    info.outputPath("desktop-generation-latency.json"),
    JSON.stringify(
      { timesMs: times, p95Ms: p95, warmups: 2, input: "synthetic normal-a4" },
      null,
      2,
    ),
  );
  expect(p95).toBeLessThanOrEqual(5000);
});
