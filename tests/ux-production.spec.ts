import { test, expect, type Page } from "@playwright/test";
import { PDFDocument } from "pdf-lib";
import { readFile } from "node:fs/promises";
async function numberedPdf(count = 6) {
  const doc = await PDFDocument.create();
  for (let i = 0; i < count; i++) {
    const p = doc.addPage([300 + i * 10, 400]);
    p.drawText(`Sample page ${i + 1}`, { x: 30, y: 320, size: 20 });
  }
  return {
    name: "generated-pages.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from(await doc.save()),
  };
}
async function downloadResult(page: Page) {
  const waiting = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PDF", exact: true }).click();
  return PDFDocument.load(await readFile((await (await waiting).path())!));
}
async function source(page: Page, tool: string) {
  await page.goto("/");
  await page.getByRole("button", { name: tool, exact: true }).click();
  await page
    .locator("#pdf-file")
    .setInputFiles("tests/fixtures/organize/ten.pdf");
}
test("split ranges, download ZIP, child edit, undo and source retention", async ({
  page,
}, info) => {
  await source(page, "Split a PDF");
  await page.getByLabel("Range 1 to", { exact: true }).fill("5");
  await page.getByRole("button", { name: "+ Add range", exact: true }).click();
  await page.getByLabel("Range 2 from", { exact: true }).fill("6");
  await page.getByLabel("Range 2 to", { exact: true }).fill("10");
  await page.getByRole("button", { name: "Split PDF →", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Your PDF is ready", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: `docs/evidence/ux-${info.project.name}-results.png`,
    fullPage: true,
  });
  const d = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download all PDFs (ZIP)", exact: true })
    .click();
  const downloaded = await d;
  await downloaded.saveAs(`docs/evidence/ux-${info.project.name}.zip`);
  for (const n of ["01", "02"]) {
    const individual = page.waitForEvent("download");
    await page
      .getByRole("button", {
        name: `Save result ten-part-${n}.pdf`,
        exact: true,
      })
      .click();
    await (
      await individual
    ).saveAs(`docs/evidence/ux-${info.project.name}-part-${n}.pdf`);
  }
  await page
    .getByRole("button", {
      name: "Continue editing ten-part-02.pdf",
      exact: true,
    })
    .click();
  await page
    .getByRole("dialog", { name: "Continue editing", exact: true })
    .getByRole("button", { name: "Organize PDF", exact: true })
    .click();
  await page.getByRole("button", { name: "Select pages", exact: true }).click();
  await page
    .getByRole("button", { name: "Select original page 1", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Rotate selected 90°", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Apply page changes", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your PDF is ready", exact: true }),
  ).toBeVisible();
  await page.locator(".session-history summary").click();
  await page.getByRole("button", { name: /^Undo Organize pages/ }).click();
  await expect(page.getByText("Page 1 of 5", { exact: true })).toBeVisible();
  await page.locator(".result-files summary").click();
  await page
    .getByRole("button", { name: "Continue editing ten.pdf", exact: true })
    .click();
  await page
    .getByRole("dialog", { name: "Continue editing", exact: true })
    .getByRole("button", { name: "Read PDF", exact: true })
    .click();
  await expect(page.getByText("Page 1 of 10", { exact: true })).toBeVisible();
});
test("merge real output with unchanged page count", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Combine PDFs", exact: true }).click();
  await page
    .locator("#combine-files")
    .setInputFiles([
      "tests/fixtures/organize/ten.pdf",
      "tests/fixtures/plain.pdf",
    ]);
  await page
    .getByRole("button", { name: "Apply combine", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your PDF is ready", exact: true }),
  ).toBeVisible();
  const d = page.waitForEvent("download");
  await page
    .locator(".delivery")
    .getByRole("button", { name: "Download PDF", exact: true })
    .click();
  const file = await d;
  const pdf = await PDFDocument.load(await readFile((await file.path())!));
  expect(pdf.getPageCount()).toBe(
    10 +
      (
        await PDFDocument.load(await readFile("tests/fixtures/plain.pdf"))
      ).getPageCount(),
  );
});
test("mobile selection grid, draft undo, guarded navigation and no overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await source(page, "Organize pages");
  await page.screenshot({
    path: "docs/evidence/ux-mobile-organize.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Select pages", exact: true }).click();
  await page
    .getByRole("button", { name: "Select original page 1", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Rotate selected 90°", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Undo draft change", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Apply page changes", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Rotate selected 90°", exact: true })
    .click();
  await page.getByRole("button", { name: "← All tools", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page
    .getByRole("button", { name: "Discard task and leave", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Simple PDF tools. Clear choices for your files.",
    }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "docs/evidence/ux-mobile-home.png",
    fullPage: true,
  });
});
test("images create downloadable PDF through the real workflow", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByRole("button", { name: "Turn Photos into PDF", exact: true })
    .click();
  await page
    .locator("#photo-files")
    .setInputFiles("tests/fixtures/photos/red.jpg");
  await page
    .getByRole("button", { name: "Convert to PDF →", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your PDF is ready", exact: true }),
  ).toBeVisible();
  const d = page.waitForEvent("download");
  await page
    .locator(".delivery")
    .getByRole("button", { name: "Download PDF", exact: true })
    .click();
  const file = await d;
  expect(
    (
      await PDFDocument.load(await readFile((await file.path())!))
    ).getPageCount(),
  ).toBe(1);
});

test("offline split and download, invalid range does not lose source", async ({
  page,
  context,
  browserName,
}) => {
  await source(page, "Split a PDF");
  await expect(page.getByLabel("Range 1 from", { exact: true })).toBeVisible();
  if (browserName === "webkit")
    await context.route(/^https?:/, (route) => route.abort());
  else await context.setOffline(true);
  await page.getByLabel("Range 1 to", { exact: true }).fill("99");
  await expect(
    page.getByRole("button", { name: "Split PDF →", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("combobox", { name: "Split mode", exact: true })
    .selectOption("each");
  await page.getByRole("button", { name: "Split PDF →", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Your PDF is ready", exact: true }),
  ).toBeVisible({ timeout: 30000 });
  const zip = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download all PDFs (ZIP)", exact: true })
    .click();
  expect(await (await zip).path()).toBeTruthy();
});

test("single split result owns primary download and preview even from a generated source", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Combine PDFs", exact: true }).click();
  await page
    .locator("#combine-files")
    .setInputFiles([
      "tests/fixtures/organize/ten.pdf",
      "tests/fixtures/plain.pdf",
    ]);
  await expect(page.locator(".merge-thumbnail img")).toHaveCount(2);
  await page
    .getByRole("button", { name: "Apply combine", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Download PDF", exact: true }),
  ).toBeVisible();
  await page.locator(".result-more-tools summary").click();
  await page
    .locator(".result-more-tools")
    .getByRole("button", { name: "Split PDF", exact: true })
    .click();
  await page.getByLabel("Range 1 to", { exact: true }).fill("3");
  await expect(page.locator('.page-strip [data-part="0"]')).toHaveCount(9);
  await page.getByRole("button", { name: "Split PDF →", exact: true }).click();
  const d = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PDF", exact: true }).click();
  expect(
    (
      await PDFDocument.load(await readFile((await (await d).path())!))
    ).getPageCount(),
  ).toBe(3);
  await expect(page.locator(".save-controls")).toHaveCount(0);
  await page.getByRole("button", { name: /^Preview result/ }).click();
  await expect(
    page.getByRole("dialog", { name: "Enlarged selected page" }),
  ).toContainText("1 / 3");
  await page
    .getByRole("button", { name: "Close preview", exact: true })
    .click();
  await expect(page.locator(".product-app")).toHaveAttribute(
    "data-screen",
    "result",
  );
});
test("fixed page groups show membership and produce bounded outputs", async ({
  page,
}) => {
  await source(page, "Split a PDF");
  await page
    .getByRole("combobox", { name: "Split mode", exact: true })
    .selectOption("fixed");
  await page.getByLabel("Pages per file", { exact: true }).fill("3");
  await expect(page.locator('.page-strip [data-part="4"]')).toHaveCount(1);
  await expect(page.locator('.page-strip [data-part="0"]')).toHaveCount(0);
  await page.getByLabel("Pages per file", { exact: true }).fill("0");
  await expect(
    page.getByRole("button", { name: "Split PDF →", exact: true }),
  ).toBeDisabled();
  await page.getByLabel("Pages per file", { exact: true }).fill("3");
  await page.getByRole("button", { name: "Split PDF →", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "4 PDFs ready to download",
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByRole("button", {
      name: "Preview result ten-part-04.pdf",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Enlarged selected page" }),
  ).toContainText("1 / 1");
});

test("drop local PDFs creates thumbnails and merges without extra network", async ({
  page,
  context,
  browserName,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Combine PDFs", exact: true }).click();
  if (browserName === "webkit")
    await context.route(/^https?:/, (r) => r.abort());
  else await context.setOffline(true);
  const files = await Promise.all(
    ["ten.pdf", "plain.pdf"].map(async (name) => ({
      name,
      data: Array.from(
        await readFile(
          name === "ten.pdf"
            ? "tests/fixtures/organize/ten.pdf"
            : "tests/fixtures/plain.pdf",
        ),
      ),
    })),
  );
  await page.locator(".combine-task").evaluate((element, inputs) => {
    const transfer = new DataTransfer();
    for (const f of inputs)
      transfer.items.add(
        new File([new Uint8Array(f.data)], f.name, { type: "application/pdf" }),
      );
    element.dispatchEvent(
      new DragEvent("drop", { bubbles: true, dataTransfer: transfer }),
    );
  }, files);
  await expect(page.locator(".merge-thumbnail img")).toHaveCount(2);
  await page
    .getByRole("button", { name: "Apply combine", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Download PDF", exact: true }),
  ).toBeVisible();
});
test("phone action bar remains usable with move panel and rotation", async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await source(page, "Organize pages");
  await page.getByRole("button", { name: "Select pages", exact: true }).click();
  await page
    .getByRole("button", { name: "Select original page 1", exact: true })
    .click();
  await page.locator(".move-options summary").click();
  await page
    .getByRole("button", { name: "Move selected down", exact: true })
    .click();
  await page.locator(".move-options summary").click();
  await page
    .getByRole("button", { name: "Rotate selected 90°", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Undo draft change", exact: true }),
  ).toBeEnabled();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: `docs/evidence/ux-round2-${info.project.name}-phone-actions.png`,
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Apply page changes", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Download PDF", exact: true }),
  ).toBeVisible();
});

test("direct page edits, precise movement, undo and guarded cancel preserve output", async ({
  page,
}, info) => {
  await page.goto("/");
  await page
    .getByRole("button", { name: "Organize pages", exact: true })
    .click();
  await page.locator("#pdf-file").setInputFiles(await numberedPdf());
  await expect(
    page.getByRole("button", { name: "Rotate selected 90°", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Rotate page 1", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Delete page 3", exact: true })
    .click();
  await expect(page.locator(".organize-row")).toHaveCount(5);
  await page
    .getByRole("button", { name: "Undo draft change", exact: true })
    .click();
  await expect(page.locator(".organize-row")).toHaveCount(6);
  await page
    .getByRole("button", { name: "Move page 2", exact: true })
    .press("Enter");
  await page.getByLabel("New position").fill("1");
  await page.getByRole("button", { name: "Move here", exact: true }).click();
  await page
    .getByRole("button", { name: "Cancel page changes", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Leave this task?" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Keep editing", exact: true }).click();
  await page.screenshot({
    path: `docs/evidence/ux3-${info.project.name}-organize.png`,
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Apply page changes", exact: true })
    .click();
  const pdf = await downloadResult(page);
  expect(pdf.getPageCount()).toBe(6);
  expect(pdf.getPage(0).getWidth()).toBe(310);
  expect(pdf.getPage(1).getWidth()).toBe(300);
  expect(pdf.getPage(1).getRotation().angle).toBe(90);
});

test("pointer handle reorders merge files and keyboard preview stays local", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Combine PDFs", exact: true }).click();
  const a = await numberedPdf(2),
    b = await numberedPdf(1);
  b.name = "second.pdf";
  await page.locator("#combine-files").setInputFiles([a, b]);
  await expect(page.locator(".merge-thumbnail img")).toHaveCount(2);
  const from = await page
    .getByRole("button", { name: "Move PDF 2", exact: true })
    .boundingBox();
  const to = await page.locator(".photo-list > li").first().boundingBox();
  await page.mouse.move(from!.x + 20, from!.y + 20);
  await page.mouse.down();
  await page.mouse.move(to!.x + 40, to!.y + 60, { steps: 8 });
  await expect(page.locator("[data-drop-target]")).toHaveCount(1);
  await page.mouse.up();
  await expect(page.locator(".photo-list > li").first()).toContainText(
    "second.pdf",
  );
  await page
    .getByRole("button", { name: "Preview PDF 1", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Enlarged selected page" }),
  ).toContainText("second.pdf");
  await page
    .getByRole("button", { name: "Close preview", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Apply combine", exact: true })
    .click();
  const pdf = await downloadResult(page);
  expect(pdf.getPages().map((p) => p.getWidth())).toEqual([300, 300, 310]);
});

test("tap page selection extracts only selected pages in source order", async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Split a PDF", exact: true }).click();
  await page.locator("#pdf-file").setInputFiles(await numberedPdf());
  await page
    .getByRole("combobox", { name: "Split mode", exact: true })
    .selectOption("selected");
  await expect(
    page.getByRole("button", { name: "Split PDF →", exact: true }),
  ).toBeDisabled();
  for (const n of [4, 2])
    await page
      .getByRole("button", { name: `Select page ${n}`, exact: true })
      .click();
  await expect(page.locator('.page-strip [aria-pressed="true"]')).toHaveCount(
    2,
  );
  await page.screenshot({
    path: `docs/evidence/ux3-${info.project.name}-split-phone.png`,
    fullPage: true,
  });
  await page.getByRole("button", { name: "Split PDF →", exact: true }).click();
  expect(
    (await downloadResult(page)).getPages().map((p) => p.getWidth()),
  ).toEqual([310, 330]);
});

test("photo paper preview follows orientation and output matches", async ({
  page,
}, info) => {
  await page.goto("/");
  await page
    .getByRole("button", { name: "Turn Photos into PDF", exact: true })
    .click();
  await page
    .locator("#photo-files")
    .setInputFiles([
      "docs/ux/public-synthetic-only/image-a.png",
      "docs/ux/public-synthetic-only/image-b.png",
    ]);
  await expect(page.locator(".photo-sheet")).toHaveCount(2);
  await page
    .getByRole("combobox", { name: "Direction", exact: true })
    .selectOption("landscape");
  expect(
    await page
      .locator(".photo-sheet")
      .first()
      .evaluate(
        (e) =>
          e.getBoundingClientRect().width > e.getBoundingClientRect().height,
      ),
  ).toBe(true);
  await page.getByRole("button", { name: "Move image 2", exact: true }).click();
  await page.getByLabel("New position").fill("1");
  await page.getByRole("button", { name: "Move here", exact: true }).click();
  await expect(page.locator(".photo-list > li").first()).toContainText(
    "image-b.png",
  );
  await page
    .getByRole("button", { name: "Rotate image 1", exact: true })
    .click();
  await page.screenshot({
    path: `docs/evidence/ux3-${info.project.name}-photos.png`,
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Convert to PDF →", exact: true })
    .click();
  const pdf = await downloadResult(page);
  expect(pdf.getPageCount()).toBe(2);
  expect(pdf.getPages().every((p) => p.getWidth() > p.getHeight())).toBe(true);
});

test("touch handle moves a page without selecting or opening the position dialog", async ({
  page,
  context,
  browserName,
}, info) => {
  test.skip(
    browserName !== "chromium",
    "CDP touch input is Chromium-specific; WebKit uses the pointer and position regressions.",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page
    .getByRole("button", { name: "Organize pages", exact: true })
    .click();
  await page.locator("#pdf-file").setInputFiles(await numberedPdf(4));
  const first = page.locator(".organize-row").first();
  const id = await first.getAttribute("data-page-id");
  const handle = page.getByRole("button", { name: "Move page 1", exact: true });
  await handle.scrollIntoViewIfNeeded();
  const from = await handle.boundingBox(),
    to = await page.locator(".organize-row").nth(1).boundingBox();
  const cdp = await context.newCDPSession(page);
  await cdp.send("Input.dispatchTouchEvent", {
    type: "touchStart",
    touchPoints: [{ x: from!.x + 20, y: from!.y + 20 }],
  });
  await cdp.send("Input.dispatchTouchEvent", {
    type: "touchMove",
    touchPoints: [{ x: to!.x + 50, y: to!.y + 70 }],
  });
  await expect(page.locator("[data-drop-target]")).toHaveCount(1);
  await cdp.send("Input.dispatchTouchEvent", {
    type: "touchEnd",
    touchPoints: [],
  });
  await expect(page.locator(".organize-row").nth(1)).toHaveAttribute(
    "data-page-id",
    id!,
  );
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator(".organize-thumbnail canvas")).toHaveCount(4);
  const actionBox = await page
    .getByRole("button", { name: "Apply page changes", exact: true })
    .boundingBox();
  expect(actionBox!.y + actionBox!.height).toBeLessThanOrEqual(844);
  await page.screenshot({
    path: `docs/evidence/ux3-${info.project.name}-touch.png`,
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Apply page changes", exact: true })
    .click();
  expect(
    (await downloadResult(page)).getPages().map((p) => p.getWidth()),
  ).toEqual([310, 300, 320, 330]);
});

test("large document keeps bounded thumbnails and range selection works", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page
    .getByRole("button", { name: "Organize pages", exact: true })
    .click();
  await page.locator("#pdf-file").setInputFiles(await numberedPdf(200));
  await expect(
    page.getByRole("button", { name: "Select pages", exact: true }),
  ).toBeVisible();
  expect(await page.locator(".organize-row").count()).toBeLessThanOrEqual(16);
  await page.getByRole("button", { name: "Select pages", exact: true }).click();
  await page.locator(".organize-range summary").click();
  await page.getByLabel("Current page positions").fill("198-200");
  await page.getByRole("button", { name: "Select range", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Select original page 200", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  expect(await page.locator(".organize-row").count()).toBeLessThanOrEqual(16);
  await page
    .getByRole("button", { name: "Rotate selected 90°", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Done selecting", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Undo draft change", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Apply page changes", exact: true }),
  ).toBeDisabled();
  await expect(page.locator('.organize-row[data-selected="true"]')).toHaveCount(
    0,
  );
});
