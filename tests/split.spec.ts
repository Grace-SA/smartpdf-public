import { test, expect, type Page } from "@playwright/test";
import { PDFDocument } from "pdf-lib";
import { readFile } from "node:fs/promises";
async function setup(page: Page, count = 10) {
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  const doc = await PDFDocument.create();
  for (let i = 1; i <= count; i++)
    doc
      .addPage([300 + i, 400 + i])
      .drawText(`Original page ${i}`, { x: 20, y: 200 });
  await page.locator("#pdf-file").setInputFiles({
    name: "source.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from(await doc.save()),
  });
  await expect(
    page.getByText(`Page 1 of ${count}`, { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Split a PDF", exact: true }).click();
}
test("SPLIT-01/04 atomic results, child edit, source switch, global undo/redo and individual save", async ({
  page,
}) => {
  await setup(page);
  let downloads = 0;
  page.on("download", () => downloads++);
  await page.getByLabel("Page groups, one per line").fill("1-3\n4-7\n8-10");
  await expect(
    page.getByText(
      "3 results · 0 pages omitted from results. The source keeps all 10 pages.",
    ),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Create split results", exact: true })
    .click();
  const results = page.getByRole("region", { name: "Session results" });
  await expect(results.locator("li")).toHaveCount(4);
  await expect(page.getByText("Page 1 of 10", { exact: true })).toBeVisible();
  expect(downloads).toBe(0);
  await results
    .getByRole("button", {
      name: "Open result source-part-02.pdf",
      exact: true,
    })
    .click();
  await expect(page.getByText("Page 1 of 4", { exact: true })).toBeVisible();
  await expect(page.locator(".page-text")).toContainText("Original page 4");
  await page
    .getByRole("button", { name: "Organize pages", exact: true })
    .click();
  await page.getByLabel("Select original page 1", { exact: true }).check();
  await page
    .getByRole("button", { name: "Rotate selected 90°", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Apply page changes", exact: true })
    .click();
  await expect(page.locator(".organize-task")).toHaveCount(0);
  await results
    .getByRole("button", { name: "Open result source.pdf", exact: true })
    .click();
  await expect(page.getByText("Page 1 of 10", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /^Undo Organize pages on/ }).click();
  await expect(page.getByText("Page 1 of 4", { exact: true })).toBeVisible();
  await expect(results.locator("li")).toHaveCount(4);
  await page
    .getByRole("button", { name: "Undo Split PDF on source.pdf", exact: true })
    .click();
  await expect(results).toHaveCount(0);
  await expect(page.getByText("Page 1 of 10", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Redo Split PDF on source.pdf", exact: true })
    .click();
  await expect(results.locator("li")).toHaveCount(4);
  const waiting = page.waitForEvent("download");
  await results
    .getByRole("button", {
      name: "Save result source-part-02.pdf",
      exact: true,
    })
    .click();
  const download = await waiting;
  expect(download.suggestedFilename()).toBe("source-part-02.pdf");
  const path = "docs/private-samples/m4/browser-part-02.pdf";
  await download.saveAs(path);
  expect((await PDFDocument.load(await readFile(path))).getPageCount()).toBe(4);
});
test("SPLIT-02 duplicates and omissions; SPLIT-03 one-page results and source survive replacement/removal", async ({
  page,
}) => {
  await setup(page);
  const input = page.getByLabel("Page groups, one per line"),
    create = page.getByRole("button", {
      name: "Create split results",
      exact: true,
    });
  for (const value of ["0", "11", "5-2", "1,1", "1-3\n3-5", "1\n\n2"]) {
    await input.fill(value);
    await expect(create).toBeDisabled();
  }
  await input.fill("1-3,5");
  await expect(
    page.getByText(
      "1 results · 6 pages omitted from results. The source keeps all 10 pages.",
    ),
  ).toBeVisible();
  await page.getByLabel("Split mode").selectOption("each");
  await create.click();
  const results = page.getByRole("region", { name: "Session results" });
  // Ten candidate readers are validated sequentially before atomic publication.
  await expect(results.locator("li")).toHaveCount(11, { timeout: 25000 });
  await results
    .getByRole("button", {
      name: "Open result source-part-02.pdf",
      exact: true,
    })
    .click();
  await expect(page.getByText("Page 1 of 1", { exact: true })).toBeVisible();
  await results
    .getByRole("button", {
      name: "Remove result source-part-01.pdf",
      exact: true,
    })
    .click();
  await page
    .getByRole("button", { name: "Remove from results", exact: true })
    .click();
  await expect(results.locator("li")).toHaveCount(10);
  await page
    .getByRole("button", {
      name: "Undo Remove result source-part-01.pdf",
      exact: true,
    })
    .click();
  await expect(results.locator("li")).toHaveCount(11);
  await page.locator("#pdf-file").setInputFiles("tests/fixtures/plain.pdf");
  await page
    .getByRole("button", { name: "Replace document", exact: true })
    .click();
  await expect(results.locator("li")).toHaveCount(11);
  await expect(page.locator(".preview-bar h2")).toHaveText("plain.pdf");
  await page.getByRole("button", { name: /^Undo Open PDF/ }).click();
  await expect(page.locator(".preview-bar h2")).toHaveText(
    "source-part-02.pdf",
  );
});
test("each-page mode over limit is rejected before generation, drafts guarded, mobile fits", async ({
  page,
}) => {
  await page.setViewportSize({ width: 360, height: 780 });
  await setup(page, 51);
  await page.getByLabel("Split mode").selectOption("each");
  await expect(
    page.getByRole("button", { name: "Create split results", exact: true }),
  ).toBeDisabled();
  await expect(page.locator(".split-task")).toContainText("at most 50 results");
  await page.getByRole("button", { name: "Combine PDFs", exact: true }).click();
  await expect(
    page.getByRole("dialog", { name: "Unapplied split groups" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Stay here", exact: true }).click();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
for (const failure of ["cancel", "crash", "late-invalid"] as const)
  test(`split ${failure} never publishes partial results`, async ({ page }) => {
    await setup(page);
    await page.getByLabel("Page groups, one per line").fill("1-3\n4-10");
    await page.evaluate((kind) => {
      const send = Worker.prototype.postMessage;
      Worker.prototype.postMessage = function (message, options) {
        if (message?.groups) {
          if (kind === "crash") {
            setTimeout(() => this.onerror?.(new ErrorEvent("error")), 50);
            return;
          }
          if (kind === "cancel") return;
          const receive = this.onmessage;
          this.onmessage = (event) => {
            if (event.data.outputs) event.data.outputs[1] = new Uint8Array([2]);
            receive?.call(this, event);
          };
          return send.call(
            this,
            message,
            options as StructuredSerializeOptions,
          );
        }
        return send.call(this, message, options as StructuredSerializeOptions);
      };
    }, failure);
    await page
      .getByRole("button", { name: "Create split results", exact: true })
      .click();
    if (failure === "cancel")
      await page
        .getByRole("button", { name: "Cancel split task", exact: true })
        .click();
    await expect(
      page.getByRole("button", { name: "Create split results", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("region", { name: "Session results" }),
    ).toHaveCount(0);
    await expect(page.getByText("Page 1 of 10", { exact: true })).toBeVisible();
    await expect(page.getByLabel("Page groups, one per line")).toHaveValue(
      "1-3\n4-10",
    );
  });
