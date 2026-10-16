import { test, expect } from "@playwright/test";
import { PDFDocument } from "pdf-lib";
async function setup(page: import("@playwright/test").Page) {
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  const pdf = await PDFDocument.create();
  for (let n = 0; n < 3; n++) pdf.addPage([300, 400]).drawText(`Page ${n + 1}`);
  await page.locator("#pdf-file").setInputFiles({
    name: "boundary.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from(await pdf.save()),
  });
  await expect(page.getByText("Page 1 of 3", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Split a PDF", exact: true }).click();
  await page.getByLabel("Page groups, one per line").fill("1\n2-3");
}
test("split timeout keeps the source and allows a successful retry", async ({
  page,
}) => {
  await setup(page);
  await page.evaluate(() => {
    const timer = window.setTimeout,
      send = Worker.prototype.postMessage;
    let first = true;
    window.setTimeout = ((fn: TimerHandler, ms?: number, ...args: unknown[]) =>
      timer(fn, ms === 120000 ? 500 : ms, ...args)) as typeof window.setTimeout;
    Worker.prototype.postMessage = function (message, options) {
      if (message?.groups && first) {
        first = false;
        return;
      }
      return send.call(this, message, options as StructuredSerializeOptions);
    };
  });
  await page
    .getByRole("button", { name: "Create split results", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("took too long");
  await expect(page.getByText("Page 1 of 3", { exact: true })).toBeVisible();
  await expect(page.locator(".split-results li")).toHaveCount(0);
  // Restore the full product deadline for the retry.
  await page.evaluate(() => {
    const timer = window.setTimeout;
    window.setTimeout = ((fn: TimerHandler, ms?: number, ...args: unknown[]) =>
      timer(
        fn,
        ms === 120000 ? 119999 : ms,
        ...args,
      )) as typeof window.setTimeout;
  });
  await page
    .getByRole("button", { name: "Create split results", exact: true })
    .click();
  await expect(page.locator(".split-results li")).toHaveCount(3, {
    timeout: 25000,
  });
});
test("redo branch requires consent and removing the active result preserves its preview", async ({
  page,
}) => {
  await setup(page);
  await page
    .getByRole("button", { name: "Create split results", exact: true })
    .click();
  await expect(page.locator(".split-results li")).toHaveCount(3, {
    timeout: 25000,
  });
  await page
    .getByRole("button", {
      name: "Undo Split PDF on boundary.pdf",
      exact: true,
    })
    .click();
  await expect(page.locator(".split-results li")).toHaveCount(0);
  await page.getByRole("button", { name: "Split a PDF", exact: true }).click();
  await page.getByLabel("Page groups, one per line").fill("1\n2-3");
  await page
    .getByRole("button", { name: "Create split results", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("Confirm discarding");
  await expect(page.locator(".split-results li")).toHaveCount(0);
  await page.getByLabel("Discard the redo branch when splitting.").check();
  await page
    .getByRole("button", { name: "Create split results", exact: true })
    .click();
  await expect(page.locator(".split-results li")).toHaveCount(3, {
    timeout: 25000,
  });
  await page
    .getByRole("button", {
      name: "Open result boundary-part-01.pdf",
      exact: true,
    })
    .click();
  await expect(page.getByText("Page 1 of 1", { exact: true })).toBeVisible();
  await page
    .getByRole("button", {
      name: "Remove result boundary-part-01.pdf",
      exact: true,
    })
    .click();
  await page
    .getByRole("button", { name: "Remove from results", exact: true })
    .click();
  await expect(page.locator(".split-results li")).toHaveCount(2);
  await expect(page.getByText("Page 1 of 1", { exact: true })).toBeVisible();
  await page
    .getByRole("button", {
      name: "Undo Remove result boundary-part-01.pdf",
      exact: true,
    })
    .click();
  await expect(page.locator(".split-results li")).toHaveCount(3);
});
