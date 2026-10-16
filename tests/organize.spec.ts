import { test, expect } from "@playwright/test";
import { PDFDocument, PDFName } from "pdf-lib";
import { readFile } from "node:fs/promises";

for (const failure of ["cancel", "timeout", "transfer"] as const)
  test(`organize ${failure} preserves current document and draft`, async ({
    page,
  }) => {
    await setup(page);
    await page
      .getByRole("button", { name: "Rotate selected 90°", exact: true })
      .click();
    await page.evaluate((kind) => {
      if (kind === "transfer") {
        const original = Worker.prototype.postMessage;
        Worker.prototype.postMessage = function (message, options) {
          if (message?.plan) throw Error("Synthetic transfer failure");
          return original.call(
            this,
            message,
            options as StructuredSerializeOptions,
          );
        };
      } else {
        FileReader.prototype.readAsArrayBuffer = function () {};
        if (kind === "timeout") {
          const original = window.setTimeout;
          window.setTimeout = ((
            handler: TimerHandler,
            ms?: number,
            ...args: unknown[]
          ) =>
            original(
              handler,
              ms === 120000 ? 100 : ms,
              ...args,
            )) as typeof window.setTimeout;
        }
      }
    }, failure);
    await page
      .getByRole("button", { name: "Apply page changes", exact: true })
      .click();
    if (failure === "cancel")
      await page
        .getByRole("button", { name: "Cancel organize task", exact: true })
        .click();
    await expect(
      page.getByRole("region", { name: "Organize pages" }).getByRole("alert"),
    ).toContainText(/unchanged/);
    await expect(page.getByText("Page 1 of 10", { exact: true })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Apply page changes", exact: true }),
    ).toBeEnabled();
    await expect(
      page.getByRole("button", { name: "Save PDF", exact: true }),
    ).toHaveCount(0);
  });
async function setup(page: import("@playwright/test").Page) {
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await page
    .locator("#pdf-file")
    .setInputFiles("tests/fixtures/organize/ten.pdf");
  await expect(page.getByText("Page 1 of 10", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Organize pages", exact: true })
    .click();
  await page
    .getByRole("checkbox", { name: "Select original page 1", exact: true })
    .check();
}
test("M3 touch-sized layout fits 360 pixels", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await setup(page);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(360);
  await expect(
    page.getByRole("button", { name: "Apply page changes", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("region", { name: "Organize pages" })
    .screenshot({ path: "docs/evidence/m3-mobile-layout.png" });
});
test("phone cards select by thumbnail and controls stay compact in both orientations", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setup(page);
  await page
    .getByRole("button", { name: "Clear selection", exact: true })
    .click();
  const first = page.locator(".organize-row").first();
  await first.locator(".organize-thumbnail").click();
  await expect(first.getByRole("checkbox")).toBeChecked();
  await expect(first).toHaveAttribute("data-selected", "true");
  await page
    .getByRole("button", { name: "Rotate selected 90°", exact: true })
    .click();
  await expect(first).toContainText("90° added rotation");
  for (const size of [
    { width: 390, height: 844 },
    { width: 844, height: 390 },
  ]) {
    await page.setViewportSize(size);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(size.width);
    for (const name of [
      "Move selected up",
      "Move selected down",
      "Rotate selected 90°",
      "Delete selected pages",
      "Apply page changes",
    ]) {
      const control = page.getByRole("button", { name, exact: true });
      expect((await control.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    }
    expect(
      await page
        .locator(".organize-tools")
        .evaluate((e) => e.getBoundingClientRect().height),
    ).toBeLessThan(200);
  }
  await page
    .getByRole("button", { name: "Apply page changes", exact: true })
    .click();
  await expect(page.locator(".organize-task")).toHaveCount(0);
});
test("ORGANIZE-01/02 offline move delete rotate save and stable-ID undo redo", async ({
  page,
  context,
  browserName,
}, info) => {
  await setup(page);
  await context.setOffline(browserName !== "webkit");
  const panel = page.getByRole("region", { name: "Organize pages" });
  await panel
    .getByRole("button", { name: "Clear selection", exact: true })
    .click();
  const viewport = panel.getByRole("group", { name: "Draft page thumbnails" });
  await viewport.evaluate((e) => (e.scrollTop = e.scrollHeight));
  const last = panel.getByRole("checkbox", {
    name: "Select original page 10",
    exact: true,
  });
  await last.check();
  const stableId = await last
    .locator("xpath=../..")
    .getAttribute("data-page-id");
  await panel
    .getByRole("button", { name: "Move selected to position", exact: true })
    .click();
  await panel
    .getByRole("button", { name: "Clear selection", exact: true })
    .click();
  await viewport.evaluate((e) => (e.scrollTop = e.scrollHeight));
  await panel
    .getByRole("checkbox", { name: "Select original page 8", exact: true })
    .check();
  await panel
    .getByRole("checkbox", { name: "Select original page 9", exact: true })
    .check();
  await panel
    .getByRole("button", { name: "Delete selected pages", exact: true })
    .click();
  await viewport.evaluate((e) => (e.scrollTop = 0));
  await panel
    .getByRole("checkbox", { name: "Select original page 4", exact: true })
    .check();
  await panel
    .getByRole("button", { name: "Rotate selected 90°", exact: true })
    .click();
  await panel
    .getByRole("button", { name: "Apply page changes", exact: true })
    .click();
  await expect(panel).toHaveCount(0);
  await expect(page.getByText("Page 1 of 8", { exact: true })).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Save PDF", exact: true }).click();
  const path = info.outputPath("organized.pdf");
  await (await download).saveAs(path);
  const out = await PDFDocument.load(await readFile(path));
  expect(out.getPages().map((p) => p.getWidth())).toEqual([
    390, 300, 310, 320, 330, 340, 350, 360,
  ]);
  expect(out.getPage(4).getRotation().angle).toBe(180);
  await page
    .getByRole("button", { name: "Organize pages", exact: true })
    .click();
  await expect(page.locator(".organize-row").first()).toHaveAttribute(
    "data-page-id",
    stableId!,
  );
  await page
    .getByRole("button", { name: "Cancel page changes", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Undo Organize pages", exact: true })
    .click();
  await expect(page.getByText("Page 1 of 10", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Redo Organize pages", exact: true })
    .click();
  await expect(page.getByText("Page 1 of 8", { exact: true })).toBeVisible();
});
test("keyboard moves, all-page deletion protection and cancel leave source unchanged", async ({
  page,
}) => {
  await setup(page);
  const first = page.getByRole("checkbox", {
    name: "Select original page 1",
    exact: true,
  });
  await first.focus();
  await page.keyboard.press("Alt+ArrowDown");
  await expect(page.locator(".organize-row").nth(1)).toContainText(
    "Original page 1",
  );
  await page
    .getByRole("button", { name: "Select all pages", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Delete selected pages", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("Keep at least one page");
  await page
    .getByRole("button", { name: "Cancel page changes", exact: true })
    .click();
  await expect(page.getByText("Page 1 of 10", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Save PDF", exact: true }),
  ).toHaveCount(0);
});
test("100-page virtual list bounds canvases and preserves offscreen selection", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  const doc = await PDFDocument.create();
  for (let i = 0; i < 100; i++) doc.addPage().drawText(`Page ${i + 1}`);
  await page.locator("#pdf-file").setInputFiles({
    name: "hundred.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from(await doc.save()),
  });
  await expect(page.getByText("Page 1 of 100", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Organize pages", exact: true })
    .click();
  await page
    .getByRole("checkbox", { name: "Select original page 1", exact: true })
    .check();
  await page
    .getByRole("checkbox", { name: "Select original page 1", exact: true })
    .check();
  const viewport = page.getByRole("group", { name: "Draft page thumbnails" });
  await expect(viewport.locator("canvas").first()).toBeVisible();
  expect(await viewport.locator(".organize-row").count()).toBeLessThanOrEqual(
    8,
  );
  await viewport.evaluate((e) => (e.scrollTop = e.scrollHeight));
  await expect(
    page.getByRole("checkbox", {
      name: "Select original page 100",
      exact: true,
    }),
  ).toBeVisible();
  expect(await viewport.locator("canvas").count()).toBeLessThanOrEqual(8);
  await viewport.evaluate((e) => (e.scrollTop = 0));
  await expect(
    page.getByRole("checkbox", { name: "Select original page 1", exact: true }),
  ).toBeChecked();
});
test("switching tasks confirms unapplied draft and retains old document", async ({
  page,
}) => {
  await setup(page);
  await page
    .getByRole("button", { name: "Rotate selected 90°", exact: true })
    .click();
  await page.getByRole("button", { name: "Combine PDFs", exact: true }).click();
  await expect(
    page.getByRole("dialog", { name: "Unapplied page changes" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Stay here", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "Organize pages" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Combine PDFs", exact: true }).click();
  await page
    .getByRole("button", { name: "Discard changes", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Combine PDFs" }),
  ).toBeVisible();
  await expect(page.getByText("Page 1 of 10", { exact: true })).toBeVisible();
});

test("processing locks keyboard reordering and retains draft after cancellation", async ({
  page,
}) => {
  await setup(page);
  await page
    .getByRole("checkbox", { name: "Select original page 1", exact: true })
    .check();
  await page
    .getByRole("button", { name: "Rotate selected 90°", exact: true })
    .click();
  const order = await page
    .locator(".organize-row")
    .evaluateAll((rows) => rows.map((r) => r.getAttribute("data-page-id")));
  await page.evaluate(() => {
    FileReader.prototype.readAsArrayBuffer = function () {};
  });
  await page
    .getByRole("button", { name: "Apply page changes", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Cancel organize task", exact: true }),
  ).toBeVisible();
  const list = page.getByRole("group", { name: "Draft page thumbnails" });
  await list.focus();
  await page.keyboard.press("Alt+ArrowDown");
  expect(
    await page
      .locator(".organize-row")
      .evaluateAll((rows) => rows.map((r) => r.getAttribute("data-page-id"))),
  ).toEqual(order);
  const cancel = page.getByRole("button", {
    name: "Cancel organize task",
    exact: true,
  });
  await cancel.focus();
  await page.keyboard.press("Shift+Tab");
  await expect(list).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(cancel).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator(".organize-row").first()).toContainText(
    "90° added rotation",
  );
});

test("draft undo restores deleted selection and rotation; a new edit clears redo", async ({
  page,
}) => {
  await setup(page);
  await page
    .getByRole("button", { name: "Cancel page changes", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Organize pages", exact: true })
    .click();
  await expect(page.locator(".organize-count")).toContainText("0 selected");
  const select = page.getByRole("checkbox", {
    name: "Select original page 2",
    exact: true,
  });
  await select.check();
  await page
    .getByRole("button", { name: "Rotate selected 90°", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Delete selected pages", exact: true })
    .click();
  await expect(page.locator(".organize-count")).toContainText("9 pages");
  await page
    .getByRole("button", { name: "Undo draft change", exact: true })
    .click();
  await expect(select).toBeChecked();
  await expect(select.locator("xpath=ancestor::label")).toContainText(
    "90° added rotation",
  );
  await page
    .getByRole("button", { name: "Undo draft change", exact: true })
    .click();
  await expect(select.locator("xpath=ancestor::label")).toContainText(
    "0° added rotation",
  );
  await page
    .getByRole("button", { name: "Redo draft change", exact: true })
    .click();
  await expect(select.locator("xpath=ancestor::label")).toContainText(
    "90° added rotation",
  );
  await page
    .getByRole("button", { name: "Move selected down", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Redo draft change", exact: true }),
  ).toBeDisabled();
  await expect(page.locator(".organize-count")).toContainText(
    "Original pages: 2",
  );
});

test("associated deletion requires explicit choice and saves a valid result", async ({
  page,
}) => {
  const { PDFName } = await import("pdf-lib");
  const d = await PDFDocument.create(),
    first = d.addPage(),
    second = d.addPage();
  first.drawText("Remove me");
  second.drawText("Keep me");
  second.node.set(
    PDFName.of("Annots"),
    d.context.obj([
      d.context.register(
        d.context.obj({
          Type: "Annot",
          Subtype: "Link",
          Rect: [0, 0, 10, 10],
          P: second.ref,
          Dest: [first.ref, "Fit"],
        }),
      ),
    ]),
  );
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await page.locator("#pdf-file").setInputFiles({
    name: "links.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from(await d.save()),
  });
  await page
    .getByRole("button", { name: "Organize pages", exact: true })
    .click();
  await page
    .getByRole("checkbox", { name: "Select original page 1", exact: true })
    .check();
  await page
    .getByRole("button", { name: "Delete selected pages", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Apply page changes", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("still refers");
  await page
    .getByRole("checkbox", { name: /Adjust associations for deleted pages/ })
    .check();
  await page
    .getByRole("button", { name: "Apply page changes", exact: true })
    .click();
  await expect(page.locator(".organize-task")).toHaveCount(0);
  await expect(page.getByText("Page 1 of 1", { exact: true })).toBeVisible();
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Save PDF", exact: true }).click(),
  ]);
  const out = await PDFDocument.load(await readFile((await download.path())!));
  expect(out.getPageCount()).toBe(1);
});

for (const kind of ["standard", "print-range"] as const)
  test(`organize preflight rejects ${kind} before opening a draft`, async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.getByText("Ready for local processing")).toBeVisible();
    const bytes = await readFile(
      kind === "standard"
        ? "tests/fixtures/pdfa.pdf"
        : "tests/fixtures/organize/ten.pdf",
    );
    const doc = await PDFDocument.load(bytes);
    if (kind === "print-range")
      doc.catalog.set(
        PDFName.of("ViewerPreferences"),
        doc.context.obj({ PrintPageRange: [0, 1] }),
      );
    await page.locator("#pdf-file").setInputFiles({
      name: "read-only.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from(await doc.save()),
    });
    await expect(
      page.getByRole("button", { name: "Organize pages", exact: true }),
    ).toBeEnabled();
    await page
      .getByRole("button", { name: "Organize pages", exact: true })
      .click();
    await expect(page.getByRole("alert")).toContainText(
      "Page organizing is unavailable",
    );
    await expect(page.getByRole("alert")).toContainText(
      kind === "standard" ? "standard" : "print-page ranges",
    );
    await expect(
      page.getByRole("region", { name: "Organize pages" }),
    ).toHaveCount(0);
    await expect(page.locator(".canvas-host canvas")).toHaveCount(1);
    await expect(page.getByRole("button", { name: "Next" })).toBeEnabled();
  });

test("organize preflight can be cancelled and retried without changing the PDF", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await page
    .locator("#pdf-file")
    .setInputFiles("tests/fixtures/organize/ten.pdf");
  await expect(page.getByText("Page 1 of 10", { exact: true })).toBeVisible();
  await page.evaluate(() => {
    Reflect.set(window, "__savedRead", FileReader.prototype.readAsArrayBuffer);
    FileReader.prototype.readAsArrayBuffer = function () {};
  });
  await page
    .getByRole("button", { name: "Organize pages", exact: true })
    .click();
  await expect(
    page.getByText("Checking whether this PDF can be organized…"),
  ).toBeVisible();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "Organize pages" }),
  ).toHaveCount(0);
  await expect(page.getByText("Page 1 of 10", { exact: true })).toBeVisible();
  await page.evaluate(() => {
    FileReader.prototype.readAsArrayBuffer = Reflect.get(window, "__savedRead");
  });
  await page
    .getByRole("button", { name: "Organize pages", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Organize pages" }),
  ).toBeVisible();
});
