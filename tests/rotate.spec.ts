import { expect, test, type Page } from "@playwright/test";
import { PDFDocument } from "pdf-lib";
import { readFile } from "node:fs/promises";
const root = "tests/fixtures/m5/";

for (const width of [390, 1280])
  test(`completion returns to the result header after scrolling the editor at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 600 });
    await open(page);
    await page
      .getByRole("button", { name: "Rotate page 1 right", exact: true })
      .click();
    const create = page.getByRole("button", {
      name: "Create PDF →",
      exact: true,
    });
    if (width > 800)
      await create.evaluate((element) =>
        element.scrollIntoView({ block: "start" }),
      );
    else await page.evaluate(() => window.scrollTo(0, 300));
    expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(50);
    await create.click();
    const result = page.getByRole("region", { name: "Completed task" });
    await expect(result).toBeVisible();
    await expect(result.getByRole("heading", { level: 1 })).toBeInViewport({
      timeout: 3000,
    });
    await expect(result.getByRole("heading", { level: 1 })).toBeFocused();
    await expect(
      result.getByRole("button", { name: "Download PDF", exact: true }),
    ).toBeInViewport();
    await expect
      .poll(() => page.evaluate(() => window.scrollY), { timeout: 3000 })
      .toBe(0);
    await expect(page.locator(".rotate-task,.rotate-submit")).toHaveCount(0);
  });
async function open(page: Page, file = "mixed-page-size.pdf") {
  await page.goto("/rotate-pdf/");
  await expect(page.locator("#pdf-file")).toBeEnabled();
  await page.locator("#pdf-file").setInputFiles(root + file);
  await expect(page.locator(".rotate-task")).toBeVisible();
  await expect(page.locator(".rotate-card canvas").first()).toBeVisible();
}
async function download(page: Page) {
  await expect(page.locator(".rotate-task, .rotate-submit")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Create PDF →", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Cancel task", exact: true }),
  ).toHaveCount(0);
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PDF", exact: true }).click();
  return PDFDocument.load(await readFile((await (await pending).path())!));
}

test("ordinary ICC color profiles need no standard-removal consent", async ({
  page,
}) => {
  await page.goto("/rotate-pdf/");
  await page
    .locator("#pdf-file")
    .setInputFiles("tests/fixtures/combine/final-color.pdf");
  await expect(page.locator(".rotate-task")).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page
    .getByRole("button", { name: "↻ Rotate right", exact: true })
    .click();
  await page.getByRole("button", { name: "Create PDF →", exact: true }).click();
  await expect(page.locator(".delivery")).toBeVisible();
  const result = await download(page);
  expect(result.getPage(0).getRotation().angle).toBe(90);
});

for (const kind of ["ordinary", "credentials"] as const)
  test(`${kind}: explicit consent stays within Rotate and produces a verified result`, async ({
    page,
  }) => {
    await page.goto("/rotate-pdf/");
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
    await expect(page.locator(".delivery,.rotate-task")).toHaveCount(0);
    await dialog
      .getByRole("button", {
        name:
          kind === "ordinary"
            ? "Create ordinary copy without standard claims"
            : "Create copy without credentials",
        exact: true,
      })
      .click();
    await expect(page.locator(".rotate-task")).toBeVisible();
    await expect(page.locator(".delivery")).toHaveCount(0);
    await page
      .getByRole("button", { name: "↻ Rotate right", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Create PDF →", exact: true })
      .click();
    await expect(page.locator(".delivery")).toBeVisible();
    await expect(page.locator(".rotate-task, .rotate-submit")).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Create PDF →", exact: true }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Cancel task", exact: true }),
    ).toHaveCount(0);
    expect((await download(page)).getPage(0).getRotation().angle).toBe(90);
  });
test("all-page default, individual rotation, undo/redo/reset and four-turn no-op", async ({
  page,
}) => {
  await open(page);
  const create = page.getByRole("button", {
    name: "Create PDF →",
    exact: true,
  });
  await expect(create).toBeDisabled();
  await expect(page.getByLabel("Apply to", { exact: true })).toHaveValue("all");
  await page
    .getByRole("button", { name: "Rotate page 1 right", exact: true })
    .click();
  await expect(page.locator('.rotate-card[data-page="1"]')).toHaveAttribute(
    "data-turns",
    "1",
  );
  await page
    .getByRole("button", { name: "Undo rotation", exact: true })
    .click();
  await expect(create).toBeDisabled();
  await page
    .getByRole("button", { name: "Redo rotation", exact: true })
    .click();
  await expect(create).toBeEnabled();
  await page
    .getByRole("button", { name: "Reset rotations", exact: true })
    .click();
  await expect(create).toBeDisabled();
  for (let i = 0; i < 4; i++)
    await page
      .getByRole("button", { name: "↻ Rotate right", exact: true })
      .click();
  await expect(create).toBeDisabled();
  await expect(page.locator(".rotate-card[data-turns='0']")).toHaveCount(
    await page.locator(".rotate-card").count(),
  );
});

for (const width of [320, 390, 1280])
  test(`${width}: selected pages, enlargement, stable thumbnails and completion`, async ({
    page,
  }, info) => {
    await page.setViewportSize({ width, height: 844 });
    await open(page);
    if (width < 800) {
      await expect(
        page.getByRole("button", { name: "↻ Rotate right", exact: true }),
      ).toBeInViewport();
      await expect(
        page.getByRole("button", { name: "Create PDF →", exact: true }),
      ).toBeInViewport();
    }
    const source = await PDFDocument.load(
      await readFile(root + "mixed-page-size.pdf"),
    );
    const firstImage = page.locator('.rotate-card[data-page="1"] canvas');
    await firstImage.evaluate((element) =>
      element.setAttribute("data-stability", "original-canvas"),
    );
    await page.getByLabel("Apply to", { exact: true }).selectOption("selected");
    await expect(
      page.getByRole("button", { name: "↶ Rotate left", exact: true }),
    ).toBeDisabled();
    await page
      .getByRole("checkbox", { name: "Select page 1", exact: true })
      .check();
    await page
      .getByRole("button", { name: "↶ Rotate left", exact: true })
      .click();
    await expect(firstImage).toHaveAttribute(
      "data-stability",
      "original-canvas",
    );
    await expect(
      page.getByRole("status").filter({ hasText: "pages changed" }),
    ).toHaveText(`1 of ${source.getPageCount()} pages changed`);
    await page
      .getByRole("button", { name: "Enlarge page 1", exact: true })
      .click();
    await expect(
      page.getByRole("dialog", { name: "Enlarged selected page", exact: true }),
    ).toBeVisible();
    await expect(page.locator(".page-detail-canvas canvas")).toBeVisible();
    await page
      .getByRole("dialog", { name: "Enlarged selected page", exact: true })
      .getByRole("button", { name: "Close preview", exact: true })
      .click();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBe(true);
    await page.screenshot({
      path: info.outputPath(`rotate-editor-${width}.png`),
      fullPage: true,
    });
    await page
      .getByRole("button", { name: "Create PDF →", exact: true })
      .click();
    await expect(page.locator(".delivery")).toBeVisible();
    const output = await download(page);
    expect(output.getPages().map((p) => p.getRotation().angle)).toEqual(
      source
        .getPages()
        .map((p, i) => (p.getRotation().angle + (i === 0 ? 270 : 0)) % 360),
    );
    await download(page);
    await page
      .getByRole("button", { name: "Choose new files", exact: true })
      .click();
    await expect(page.locator("#pdf-file")).toHaveValue("");
    await expect(page.locator(".rotate-task, .delivery")).toHaveCount(0);
  });

test("range selection is validated, 200 pages stay virtualized, selection does not change the PDF", async ({
  page,
}) => {
  await open(page, "200-pages.pdf");
  expect(await page.locator(".rotate-card").count()).toBeLessThan(50);
  await page.getByLabel("Apply to", { exact: true }).selectOption("selected");
  await page.getByText("Select a page range", { exact: true }).click();
  await page.getByLabel("Page numbers", { exact: true }).fill("201");
  await page.getByRole("button", { name: "Select range", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("1 to 200");
  await page.getByLabel("Page numbers", { exact: true }).fill("199-200");
  await page.getByRole("button", { name: "Select range", exact: true }).click();
  await expect(
    page.getByRole("checkbox", { name: "Select page 200", exact: true }),
  ).toBeChecked();
  await expect(
    page.getByRole("button", { name: "Create PDF →", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "↻ Rotate right", exact: true })
    .click();
  await page.getByRole("button", { name: "Create PDF →", exact: true }).click();
  await expect(page.locator(".delivery")).toBeVisible();
  const output = await download(page);
  expect(output.getPageCount()).toBe(200);
  expect(output.getPage(198).getRotation().angle).toBe(90);
  expect(output.getPage(197).getRotation().angle).toBe(0);
});

test("a dirty draft stays on cancel, discards explicitly, and ready rotation works offline", async ({
  page,
  context,
}, info) => {
  await open(page, "normal-a4.pdf");
  await page
    .getByRole("button", { name: "↻ Rotate right", exact: true })
    .click();
  await page.getByRole("button", { name: "← All tools", exact: true }).click();
  await expect(page.locator("#leave-task-description")).toHaveText(
    "Your page rotation changes will be discarded. Your original files will not be deleted.",
  );
  await page
    .getByRole("dialog", { name: "Leave this task?", exact: true })
    .getByRole("button", { name: "Keep editing", exact: true })
    .click();
  await expect(page.locator('.rotate-card[data-page="1"]')).toHaveAttribute(
    "data-turns",
    "1",
  );
  await context.route(/^https?:/, (route) =>
    route.abort("internetdisconnected"),
  );
  if (info.project.name === "chromium") await context.setOffline(true);
  await page.getByRole("button", { name: "Create PDF →", exact: true }).click();
  await expect(page.locator(".delivery")).toBeVisible();
  expect((await download(page)).getPageCount()).toBe(2);
});

for (const name of [
  "zero-pages.pdf",
  "corrupted.pdf",
  "encrypted.pdf",
  "large-50mb.pdf",
  "100mb.pdf",
])
  test(`safe refusal and working replacement picker: ${name}`, async ({
    page,
  }, info) => {
    test.skip(
      info.project.name === "webkit" && /50mb|100mb/.test(name),
      "Oversized-input allocation is exercised in Chromium and the core tests.",
    );
    await page.goto("/rotate-pdf/");
    await page.locator("#pdf-file").setInputFiles(root + name);
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page.locator(".rotate-task")).toHaveCount(0);
    await page.locator("#pdf-file").setInputFiles(root + "normal-a4.pdf");
    await expect(page.locator(".rotate-task")).toBeVisible();
  });

test("generation failure keeps a reusable draft and retry completes", async ({
  page,
}) => {
  await open(page, "normal-a4.pdf");
  await page
    .getByRole("button", { name: "↻ Rotate right", exact: true })
    .click();
  await page.evaluate(() => {
    const Original = window.Worker;
    Object.defineProperty(window, "__rotateWorker", {
      value: Original,
      configurable: true,
    });
    window.Worker = class extends Original {
      postMessage() {
        queueMicrotask(() =>
          this.onerror?.(
            new ErrorEvent("error", {
              message: "Synthetic worker failure",
              cancelable: true,
            }),
          ),
        );
      }
    };
  });
  await page.getByRole("button", { name: "Create PDF →", exact: true }).click();
  await expect(
    page.getByRole("dialog", { name: "PDF needs attention", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Back to editing", exact: true })
    .click();
  await expect(page.locator('.rotate-card[data-page="1"]')).toHaveAttribute(
    "data-turns",
    "1",
  );
  await expect(
    page.getByRole("button", { name: "Create PDF →", exact: true }),
  ).toBeEnabled();
  await page.evaluate(() => {
    window.Worker = (
      window as unknown as { __rotateWorker: typeof Worker }
    ).__rotateWorker;
  });
  await page.getByRole("button", { name: "Create PDF →", exact: true }).click();
  await expect(page.locator(".delivery")).toBeVisible();
});

test("cancel pending generation preserves the draft, and explicit discard clears it", async ({
  page,
}) => {
  await open(page, "normal-a4.pdf");
  await page
    .getByRole("button", { name: "↻ Rotate right", exact: true })
    .click();
  await page.evaluate(() => {
    const Original = window.Worker;
    window.Worker = class extends Original {
      postMessage() {}
    };
  });
  await page.getByRole("button", { name: "Create PDF →", exact: true }).click();
  await page
    .getByRole("button", { name: "Cancel processing", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("Cancelled");
  await page
    .getByRole("button", { name: "Back to editing", exact: true })
    .click();
  await expect(page.locator('.rotate-card[data-page="1"]')).toHaveAttribute(
    "data-turns",
    "1",
  );
  await page.getByRole("button", { name: "← All tools", exact: true }).click();
  await page
    .getByRole("button", { name: "Discard task and leave", exact: true })
    .click();
  await expect(page.locator(".tool-home")).toBeVisible();
  await expect(page.locator(".rotate-task, dialog[open]")).toHaveCount(0);
});
