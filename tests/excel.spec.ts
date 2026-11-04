import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { PDFDocument, StandardFonts } from "pdf-lib";
const fixtureRoot = ".research/excel/browser-fixtures";

test("a missing Excel module can retry without a blank page", async ({
  page,
}) => {
  await page.route("**/assets/ExcelPage-*.js", (route) => route.abort());
  await page.goto("/excel-to-pdf/");
  await expect(
    page.getByRole("button", {
      name: "Retry opening Excel to PDF",
      exact: true,
    }),
  ).toBeVisible();
  await page.unroute("**/assets/ExcelPage-*.js");
  await page
    .getByRole("button", { name: "Retry opening Excel to PDF", exact: true })
    .click();
  await expect(page.locator("#excel-file")).toBeVisible();
});
test.beforeAll(() => {
  execFileSync(process.platform === "win32" ? "python" : "python3", [
    "-B",
    "scripts/excel/fixtures.py",
    fixtureRoot,
  ]);
});

async function mock(page: Page, mode = "success") {
  const pdf = await PDFDocument.create();
  pdf.addPage();
  if (mode === "preview") {
    const font = await pdf.embedFont(StandardFonts.Helvetica);
    for (let i = 0; i < 5; i++) {
      const p = pdf.addPage();
      for (let y = 0; y < 70; y++)
        p.drawText(`Synthetic preview page ${i + 2}, row ${y + 1}`, {
          x: 20,
          y: 810 - y * 11,
          size: 9,
          font,
        });
    }
  }
  const bytes = Buffer.from(await pdf.save());
  const calls: { method: string; path: string; options?: string }[] = [];
  let counter = 0;
  await page.route("**/api/excel/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    calls.push({
      method: request.method(),
      path,
      options: request.headers()["x-excel-options"],
    });
    const send = (status: number, value: unknown) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(value),
      });
    if (path.endsWith("/session"))
      return send(mode === "offline" ? 503 : 200, {
        region: "Local test server",
        available: true,
        retentionMinutes: 60,
      });
    if (request.method() === "DELETE")
      return send(200, {
        id: "synthetic-task",
        state: "cancelled",
        warnings: [],
        cleanupPending: false,
      });
    if (path.endsWith("/jobs"))
      return send(
        mode === "full" ? 429 : 201,
        mode === "full"
          ? { error: "The conversion queue is full. Try again shortly." }
          : { id: `synthetic-${++counter}`, state: "created", warnings: [] },
      );
    if (path.endsWith("/input")) return send(202, { state: "queued" });
    if (path.endsWith("/result"))
      return route.fulfill({
        status: 200,
        contentType: "application/pdf",
        body: bytes,
      });
    return send(200, {
      id: `synthetic-${counter}`,
      state:
        mode === "slow"
          ? "converting"
          : mode === "reject"
            ? "failed"
            : "succeeded",
      pages: mode === "preview" ? 6 : 1,
      warnings: ["Check totals and print areas."],
      error:
        mode === "reject"
          ? "Externally linked content is not supported."
          : undefined,
    });
  });
  return calls;
}
async function choose(page: Page, file = "selection.xlsx") {
  await page.locator("#excel-file").setInputFiles(`${fixtureRoot}/${file}`);
  await expect(
    page.getByRole("group", { name: "Worksheets and page layout" }),
  ).toBeVisible();
}
for (const width of [320, 390, 1280]) {
  test(`${width}: local selection, hidden sheets, settings and explicit upload`, async ({
    page,
  }, info) => {
    const calls = await mock(page);
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/excel-to-pdf/");
    await expect(
      page.getByRole("heading", {
        name: "Excel to PDF",
        exact: true,
        level: 1,
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", {
        name: "Upload and generate PDF",
        exact: true,
      }),
    ).toHaveCount(0);
    await choose(page);
    await expect(page.getByLabel("Report", { exact: true })).toBeChecked();
    await expect(page.getByLabel("Other", { exact: true })).toBeChecked();
    await expect(
      page.getByText("1 hidden worksheet(s) excluded."),
    ).toBeVisible();
    await expect(page.getByLabel("Hidden", { exact: true })).toHaveCount(0);
    expect(calls.filter((call) => call.method !== "GET")).toEqual([]);
    await page.getByLabel("Other", { exact: true }).uncheck();
    await page.getByText("More page settings", { exact: true }).click();
    await page.getByLabel("Scaling", { exact: true }).selectOption("width");
    await page
      .getByLabel("Orientation", { exact: true })
      .selectOption("landscape");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    if (width < 900) {
      const primary = page.getByRole("button", {
        name: "Upload and generate PDF",
        exact: true,
      });
      await expect(primary).toHaveCSS("position", "fixed");
      const box = (await primary.boundingBox())!;
      expect(box.y).toBeGreaterThanOrEqual(800);
      expect(box.y + box.height).toBeLessThanOrEqual(900);
    }
    await page.screenshot({
      path: info.outputPath(`excel-selected-${width}.png`),
      fullPage: true,
    });
    await page
      .getByRole("button", { name: "Upload and generate PDF", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Your PDF is ready" }),
    ).toBeAttached();
    const upload = calls.find((call) => call.path.endsWith("/input"))!;
    expect(JSON.parse(upload.options!)).toEqual({
      sheets: [0],
      orientation: "landscape",
      paper: "keep",
      scale: "width",
    });
    const close = page.getByRole("button", { name: /Close preview/i });
    if (await close.count()) await close.click();
    await expect(
      page.getByRole("link", { name: "Download PDF", exact: true }),
    ).toBeVisible();
    if (width < 900) {
      await expect(
        page.getByRole("link", { name: "Download PDF", exact: true }),
      ).toHaveCSS("position", "fixed");
      await page
        .getByRole("button", { name: "Adjust pagination", exact: true })
        .click();
      await page.getByText("More page settings", { exact: true }).click();
      await page
        .getByLabel("Paper size", { exact: true })
        .selectOption("Letter");
      await expect(
        page.getByRole("link", { name: "Download PDF", exact: true }),
      ).toHaveCount(0);
      await expect(
        page.getByRole("button", { name: "Update PDF", exact: true }),
      ).toHaveCSS("position", "fixed");
    }
  });
}
test("empty selection blocks upload, and unsupported file / corrupt workbook can be replaced", async ({
  page,
}) => {
  const calls = await mock(page);
  await page.goto("/excel-to-pdf/");
  await choose(page);
  await page.getByLabel("Report", { exact: true }).uncheck();
  await page.getByLabel("Other", { exact: true }).uncheck();
  await expect(
    page.getByRole("button", { name: "Upload and generate PDF", exact: true }),
  ).toBeDisabled();
  await page.locator("#excel-file").setInputFiles({
    name: "bad.xlsx",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("broken"),
  });
  await expect(page.getByRole("alert")).toContainText("valid");
  await page.locator("#excel-file").setInputFiles({
    name: "old.xls",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("old"),
  });
  await expect(page.getByRole("alert")).toContainText("one XLSX");
  await choose(page);
  expect(calls.filter((call) => call.method !== "GET")).toEqual([]);
});
test("cancel removes an active job and resets the worksheet selection", async ({
  page,
}) => {
  const calls = await mock(page, "slow");
  await page.goto("/excel-to-pdf/");
  await choose(page);
  await page
    .getByRole("button", { name: "Upload and generate PDF", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Cancel conversion" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Cancel conversion" }).click();
  await expect(
    page.getByText("Temporary files deleted. Your original is unchanged."),
  ).toBeVisible();
  expect(calls.some((call) => call.method === "DELETE")).toBe(true);
  await expect(
    page.getByRole("group", { name: "Worksheets and page layout" }),
  ).toHaveCount(0);
});
for (const mode of ["reject", "full", "offline"])
  test(`${mode}: actionable error without false result`, async ({ page }) => {
    await mock(page, mode);
    await page.goto("/excel-to-pdf/");
    await choose(page);
    const start = page.getByRole("button", {
      name: "Upload and generate PDF",
      exact: true,
    });
    if (mode === "offline") {
      await expect(start).toBeDisabled();
      await expect(
        page.getByRole("button", { name: "Retry connection" }),
      ).toBeVisible();
    } else {
      await start.click();
      await expect(page.getByRole("alert")).toBeVisible();
    }
    await expect(
      page.getByRole("link", { name: "Download PDF", exact: true }),
    ).toHaveCount(0);
  });
test("changed settings invalidate download until updated, then delete and start another workbook", async ({
  page,
}) => {
  const calls = await mock(page);
  await page.goto("/excel-to-pdf/");
  await choose(page);
  // Avoid an auto-open preview covering the result controls during this state-machine check.
  await page.route("**/assets/engine-*.js", (route) => route.abort());
  await page
    .getByRole("button", { name: "Upload and generate PDF", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your PDF is ready" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Adjust pagination" }).click();
  await page.getByText("More page settings", { exact: true }).click();
  await page.getByLabel("Scaling", { exact: true }).selectOption("page");
  await expect(
    page.getByText("Settings have changed. Update the PDF before downloading."),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Download PDF", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Update PDF", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "Download PDF", exact: true }),
  ).toBeVisible();
  expect(calls.filter((call) => call.method === "POST")).toHaveLength(2);
  expect(calls.some((call) => call.method === "DELETE")).toBe(true);
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download PDF", exact: true }).click();
  expect((await download).suggestedFilename()).toBe("selection.pdf");
  await page.getByRole("button", { name: "Delete temporary files" }).click();
  await expect(
    page.getByText("Temporary files deleted. Your original is unchanged."),
  ).toBeVisible();
  await choose(page, "print-area.xlsx");
});

test("inline PDF preview can flip pages and be disposed without late stream errors", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await mock(page, "preview");
  await page.goto("/excel-to-pdf/");
  await choose(page);
  await page
    .getByRole("button", { name: "Upload and generate PDF", exact: true })
    .click();
  await expect(
    page.locator('.excel-preview canvas[aria-label="PDF preview, page 1"]'),
  ).toBeVisible();
  for (let i = 0; i < 5; i++) {
    await page.getByRole("button", { name: "Next page", exact: true }).click();
    await expect(
      page.locator('.excel-preview canvas[aria-label="PDF preview, page 2"]'),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Previous page", exact: true })
      .click();
    await expect(
      page.locator('.excel-preview canvas[aria-label="PDF preview, page 1"]'),
    ).toBeVisible();
  }
  await page.getByRole("button", { name: "Next page", exact: true }).click();
  await page
    .getByRole("button", { name: "Adjust pagination", exact: true })
    .click();
  await page.getByText("More page settings", { exact: true }).click();
  await page
    .getByLabel("Orientation", { exact: true })
    .selectOption("landscape");
  await expect(page.locator(".excel-preview canvas")).toHaveCount(0);
  await page
    .getByRole("button", { name: "Delete temporary files", exact: true })
    .click();
  await expect(
    page.getByText("Temporary files deleted. Your original is unchanged."),
  ).toBeVisible();
  await page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      ),
  );
  expect(errors).toEqual([]);
});
