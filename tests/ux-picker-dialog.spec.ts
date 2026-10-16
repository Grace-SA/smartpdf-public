import { selectTool } from "./navigation";
import { test, expect, type Page } from "@playwright/test";
const root = "docs/ux/public-synthetic-only/";
async function pick(page: Page, id: string, files: string[]) {
  await expect(page.locator(`#${id}`)).toBeEnabled();
  // A real tap must hit the input, not depend on a label forwarding its click.
  await expect(page.locator(`#${id}`)).toBeVisible();
  expect(
    await page.locator(`#${id}`).evaluate((input) => {
      const box = input.getBoundingClientRect();
      return (
        document.elementFromPoint(
          box.x + box.width / 2,
          box.y + box.height / 2,
        ) === input
      );
    }),
  ).toBe(true);
  const chooser = page.waitForEvent("filechooser", { timeout: 5000 });
  await page.locator(`label[for="${id}"]`).tap();
  await (await chooser).setFiles(files.map((file) => root + file));
}
test("completed images → Split → Merge: real picker activation without refreshing", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  for (let round = 0; round < 2; round++) {
    await selectTool(page, "Turn Photos into PDF");
    await pick(page, "photo-files", ["image-a.png", "image-b.png"]);
    await page
      .getByRole("button", { name: "Move image 1", exact: true })
      .click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Cancel", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Convert to PDF →", exact: true })
      .click();
    await expect(page.locator(".delivery")).toBeVisible();
    const download = page.waitForEvent("download");
    await page
      .getByRole("button", { name: "Download PDF", exact: true })
      .click();
    await download;
    await selectTool(page, "Split a PDF");
    await pick(page, "pdf-file", ["demo-a.pdf"]);
    await page.getByLabel("Range 1 to", { exact: true }).fill("2");
    await page
      .getByRole("button", { name: "Split PDF →", exact: true })
      .click();
    await expect(page.locator(".delivery")).toBeVisible();
    await selectTool(page, "Combine PDFs");
    await pick(page, "combine-files", ["demo-a.pdf", "demo-b.pdf"]);
    await page
      .getByRole("button", { name: "Apply combine", exact: true })
      .click();
    await expect(page.locator(".delivery")).toBeVisible();
  }
});

for (const tool of ["images", "merge"] as const) {
  test(`${tool}: move dialog has normal action buttons and commits the selected position`, async ({
    page,
  }, info) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await selectTool(
      page,
      tool === "images" ? "Turn Photos into PDF" : "Combine PDFs",
    );
    await pick(
      page,
      tool === "images" ? "photo-files" : "combine-files",
      tool === "images"
        ? ["image-a.png", "image-b.png"]
        : ["demo-a.pdf", "demo-b.pdf"],
    );
    await page
      .getByRole("button", {
        name: `Move ${tool === "images" ? "image" : "PDF"} 1`,
        exact: true,
      })
      .click();
    const dialog = page.getByRole("dialog");
    const move = dialog.getByRole("button", { name: "Move here", exact: true });
    await expect(move).toBeDisabled();
    await dialog.getByLabel("New position").fill("3");
    await expect(move).toBeDisabled();
    await dialog.getByLabel("New position").fill("2");
    await expect(move).toBeEnabled();
    expect(
      await move.evaluate((e) => getComputedStyle(e).backgroundColor),
    ).toBe("rgb(229, 50, 45)");
    expect(await move.evaluate((e) => getComputedStyle(e).fontSize)).toBe(
      "15px",
    );
    const bounds = (await dialog.boundingBox())!;
    expect(Math.abs(bounds.x + bounds.width / 2 - 195)).toBeLessThan(2);
    await page.screenshot({
      path: info.outputPath(`ux13-${info.project.name}-${tool}-move.png`),
    });
    await move.click();
    await expect(dialog).toHaveCount(0);
    await expect(page.locator(".photo-list > li").first()).toContainText(
      tool === "images" ? "image-b.png" : "demo-b.pdf",
    );
  });
}
