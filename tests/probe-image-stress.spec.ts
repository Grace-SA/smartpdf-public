import { expect, test } from "@playwright/test";
import { PDFDocument } from "pdf-lib";
import { readFile } from "node:fs/promises";

test("repeated image generation finishes 30 fresh tasks and downloads a valid PDF", async ({
  page,
}) => {
  test.setTimeout(180000);
  await page.goto("/images-to-pdf/");
  for (let round = 0; round < 30; round++) {
    await page
      .locator("#photo-files")
      .setInputFiles("docs/ux/public-synthetic-only/image-a.png");
    await expect(
      page.getByRole("button", { name: "Preview image 1", exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Convert to PDF →", exact: true })
      .click();
    await expect(page.locator(".delivery")).toBeVisible({ timeout: 30000 });
    if (round < 29)
      await page
        .getByRole("button", { name: "Choose new files", exact: true })
        .click();
  }
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PDF", exact: true }).click();
  const file = await (await pending).path();
  expect(file).toBeTruthy();
  expect((await PDFDocument.load(await readFile(file!))).getPageCount()).toBe(
    1,
  );
});
