import { test, expect, type Page } from "@playwright/test";
import { selectTool } from "./navigation";
import { readFile } from "node:fs/promises";
import { PDFDocument } from "pdf-lib";

const root = "tests/fixtures/m5/";

async function open(page: Page, name: string) {
  await page.goto("/");
  await selectTool(page, "Compress PDF");
  await expect(page.locator("#pdf-file")).toBeEnabled({ timeout: 30000 });
  await page.locator("#pdf-file").setInputFiles(root + name);
}

async function compress(page: Page, level: string) {
  await expect(page.getByRole("radio", { name: /Recommended/ })).toBeVisible();
  if (level !== "Recommended")
    await page.getByRole("radio", { name: new RegExp(level) }).check();
  await page
    .locator(".compress-actions")
    .getByRole("button", { name: "Compress PDF", exact: true })
    .click();
  await expect(page.locator(".delivery")).toBeVisible({ timeout: 120000 });
}

test("recommended is the default and produces a verified downloadable PDF", async ({
  page,
}) => {
  await open(page, "image-heavy.pdf");
  await expect(page.getByRole("radio", { name: /Recommended/ })).toBeChecked();
  await compress(page, "Recommended");
  await expect(page.locator(".output-summary")).toContainText(/MB|KB/);
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PDF" }).click();
  const saved = await (await download).createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of saved) chunks.push(Buffer.from(chunk));
  const bytes = Buffer.concat(chunks);
  expect(bytes.byteLength).toBeLessThanOrEqual(
    (await readFile(root + "image-heavy.pdf")).byteLength,
  );
  const source = await readFile(root + "image-heavy.pdf");
  expect((await PDFDocument.load(bytes)).getPageCount()).toBe(
    (await PDFDocument.load(source)).getPageCount(),
  );
});

test("all three levels, cancellation and fresh task boundary are clear", async ({
  page,
}) => {
  await open(page, "normal-a4.pdf");
  await page.getByRole("radio", { name: /Smaller file/ }).check();
  await page
    .locator(".compress-actions")
    .getByRole("button", { name: "Compress PDF", exact: true })
    .click();
  const cancel = page.getByRole("button", { name: "Cancel processing" });
  if (await cancel.isVisible()) await cancel.click();
  await expect(page.locator(".compress-task")).toBeVisible();
  await page.getByRole("radio", { name: /Highest quality/ }).check();
  await compress(page, "Highest quality");
  await page.getByRole("button", { name: /Choose new files/ }).click();
  await expect(page.locator("#pdf-file")).toBeVisible();
  await expect(page.locator(".delivery")).toHaveCount(0);
});

for (const name of ["zero-pages.pdf", "corrupted.pdf", "encrypted.pdf"])
  test(`${name} is refused without entering compression`, async ({ page }) => {
    await open(page, name);
    await expect(page.getByRole("alert")).toBeVisible({ timeout: 30000 });
    await expect(page.locator(".compress-task")).toHaveCount(0);
  });

test("200 pages and unusual page sizes compress without changing geometry", async ({
  page,
}) => {
  for (const name of ["200-pages.pdf", "unusual-page-sizes.pdf"]) {
    await open(page, name);
    await compress(page, "Highest quality");
    await expect(page.locator(".output-summary")).toContainText(
      name.startsWith("200") ? "200 pages" : "3 pages",
    );
  }
});

test("100 MiB and 50 MiB inputs are rejected before allocation", async ({
  page,
}, info) => {
  test.skip(info.project.name === "webkit", "One-browser resource boundary");
  for (const name of ["large-50mb.pdf", "100mb.pdf"]) {
    await open(page, name);
    await expect(page.getByRole("alert")).toContainText(
      /30 MiB|larger|non-empty/i,
    );
  }
});

test("mobile layout keeps levels and primary action in one readable column", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page, "normal-a4.pdf");
  const levels = page.locator(".compression-levels > label");
  await expect(levels).toHaveCount(3);
  const first = await levels.nth(0).boundingBox();
  const second = await levels.nth(1).boundingBox();
  expect(first && second && second.y > first.y + first.height - 2).toBe(true);
  await expect(
    page
      .locator(".compress-actions")
      .getByRole("button", { name: "Compress PDF", exact: true }),
  ).toBeVisible();
});

test("a ready tab compresses with networking disabled and makes no requests", async ({
  page,
  context,
}, info) => {
  test.skip(
    info.project.name === "webkit",
    "Native offline blocks local worker URLs in WebKit",
  );
  const requests: string[] = [];
  page.on("request", (request) => requests.push(request.url()));
  await page.goto("/");
  await selectTool(page, "Compress PDF");
  await expect(page.locator(".status.ready")).toHaveText(
    "Ready for local processing",
  );
  const before = requests.length;
  await context.setOffline(true);
  await page.locator("#pdf-file").setInputFiles(root + "normal-a4.pdf");
  await compress(page, "Recommended");
  expect(
    requests
      .slice(before)
      .filter((url) => url.startsWith("http://") || url.startsWith("https://")),
  ).toEqual([]);
});
