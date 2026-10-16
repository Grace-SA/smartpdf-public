import { test, expect } from "@playwright/test";
import { PDFDocument } from "pdf-lib";
import { readFile } from "node:fs/promises";
test("jump and draft position ranges work after reorder, with enlarged rotated selection", async ({
  page,
  browserName,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  const doc = await PDFDocument.create();
  for (let i = 1; i <= 12; i++)
    doc.addPage([300, 400]).drawText(`Page ${i}`, { x: 40, y: 250 });
  await page.locator("#pdf-file").setInputFiles({
    name: "range.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from(await doc.save()),
  });
  await expect(page.getByText("Page 1 of 12", { exact: true })).toBeVisible();
  await page.getByLabel("Go to page", { exact: true }).fill("9");
  await page.getByRole("button", { name: "Go", exact: true }).click();
  await expect(page.getByText("Page 9 of 12", { exact: true })).toBeVisible();
  await page.getByLabel("Go to page", { exact: true }).fill("13");
  await page.getByLabel("Go to page", { exact: true }).press("Enter");
  await expect(page.getByRole("alert")).toContainText("from 1 to 12");
  await expect(page.getByText("Page 9 of 12", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Organize pages", exact: true })
    .click();
  await page.getByText("Select a page range", { exact: true }).click();
  const range = page.getByLabel("Current page positions");
  await range.fill("2-3, 9");
  await page.getByRole("button", { name: "Select range", exact: true }).click();
  await expect(page.locator(".organize-count")).toContainText("3 selected");
  await range.fill("3-1");
  await page.getByRole("button", { name: "Select range", exact: true }).click();
  await expect(page.locator(".organize-count")).toContainText("3 selected");
  await page.getByLabel("Move to position", { exact: true }).fill("1");
  await page
    .getByRole("button", { name: "Move selected to position", exact: true })
    .click();
  await range.fill("1-2");
  await page.getByRole("button", { name: "Select range", exact: true }).click();
  await expect(page.locator(".organize-count")).toContainText(
    "Original pages: 2, 3",
  );
  await page
    .getByRole("button", { name: "Rotate selected 90°", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Enlarge selected pages", exact: true })
    .click();
  const modal = page.getByRole("dialog", { name: "Enlarged selected page" });
  await expect(modal.getByRole("heading")).toContainText("Original page 2");
  await expect(modal.locator("canvas")).toHaveCount(1);
  await page.screenshot({
    path: `docs/evidence/usability-enlarged-${browserName}.png`,
  });
  expect(
    await modal
      .locator("canvas")
      .evaluate(
        (c) => (c as HTMLCanvasElement).width > (c as HTMLCanvasElement).height,
      ),
  ).toBe(true);
  await modal.getByRole("button", { name: "Zoom 200%", exact: true }).click();
  await expect(
    modal.getByRole("button", { name: "Zoom 200%", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await modal
    .getByRole("button", { name: "Next selected", exact: true })
    .click();
  await expect(modal.getByRole("heading")).toContainText("Original page 3");
  await expect(modal.locator("canvas")).toHaveAttribute(
    "aria-label",
    /Original page 3/,
  );
  await page.setViewportSize({ width: 844, height: 390 });
  await expect(modal.locator("canvas")).toHaveCount(1);
  expect(
    await modal.evaluate(
      (e) => e.getBoundingClientRect().width <= window.innerWidth,
    ),
  ).toBe(true);
  await modal
    .getByRole("button", { name: "Close enlarged page", exact: true })
    .click();
  await expect(modal).toHaveCount(0);
  await expect(page.locator(".organize-count")).toContainText("2 selected");
  await page
    .getByRole("button", { name: "Undo draft change", exact: true })
    .click();
  await expect(page.locator(".organize-count")).toContainText("2 selected");
});
test("ICC JPEG, transparent ICC PNG and gamma PNG generate and reopen locally", async ({
  page,
  browserName,
}) => {
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await page
    .getByRole("button", { name: "Turn Photos into PDF", exact: true })
    .click();
  const requests: string[] = [];
  await page.route(/^https?:/, (route) => {
    requests.push(route.request().url());
    return route.abort();
  });
  await page
    .locator("#photo-browse-files")
    .setInputFiles(
      ["color-linear.jpg", "color-linear.png", "color-gamma.png"].map(
        (name) => `tests/fixtures/photos/${name}`,
      ),
    );
  await expect(
    page.getByRole("button", { name: "Apply photos", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Apply photos", exact: true }).click();
  await expect(page.getByText("Page 1 of 3", { exact: true })).toBeVisible();
  for (const number of [2, 3]) {
    await page.getByLabel("Go to page", { exact: true }).fill(String(number));
    await page.getByRole("button", { name: "Go", exact: true }).click();
    await expect(
      page.getByText(`Page ${number} of 3`, { exact: true }),
    ).toBeVisible();
  }
  const waiting = page.waitForEvent("download");
  await page.getByRole("button", { name: "Save PDF", exact: true }).click();
  const file = `docs/private-samples/m1/color-browser-${browserName}.pdf`;
  await (await waiting).saveAs(file);
  expect((await PDFDocument.load(await readFile(file))).getPageCount()).toBe(3);
  expect(requests).toEqual([]);
});
