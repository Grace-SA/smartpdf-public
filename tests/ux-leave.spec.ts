import { selectTool } from "./navigation";
import { test, expect } from "@playwright/test";

test("photo import never drops a navigation click before busy state commits", async ({
  page,
}) => {
  await page.goto("/images-to-pdf/");
  await page
    .locator("#photo-files")
    .setInputFiles("docs/ux/public-synthetic-only/image-a.png");
  await expect(page.locator(".photo-list>li")).toHaveCount(1);
  await page.evaluate(() => {
    const original = FileReader.prototype.readAsArrayBuffer;
    FileReader.prototype.readAsArrayBuffer = function (blob) {
      FileReader.prototype.readAsArrayBuffer = original;
      const button = [...document.querySelectorAll("button")].find(
        (b) => b.textContent === "← All tools",
      );
      button?.click();
      original.call(this, blob);
    };
  });
  await page
    .locator("#photo-files")
    .setInputFiles("docs/ux/public-synthetic-only/image-a.png");
  const dialog = page.getByRole("dialog", {
    name: "Leave this task?",
    exact: true,
  });
  await expect(dialog).toBeVisible();
  await dialog
    .getByRole("button", { name: "Discard task and leave", exact: true })
    .click();
  await expect(page.locator(".product-app")).toHaveAttribute(
    "data-screen",
    "home",
  );
  await selectTool(page, "Turn Photos into PDF");
  await expect(page.locator(".photo-list>li")).toHaveCount(0);
});

for (const tool of ["photos", "combine", "organize", "split"] as const) {
  test(`${tool} leave confirmation is centered, safe by default and only discards on explicit choice`, async ({
    page,
  }, info) => {
    await page.goto("/");
    const name = {
      photos: "Turn Photos into PDF",
      combine: "Combine PDFs",
      organize: "Organize pages",
      split: "Split a PDF",
    }[tool];
    await selectTool(page, name);
    if (tool === "photos")
      await page
        .locator("#photo-files")
        .setInputFiles("docs/ux/public-synthetic-only/image-a.png");
    else if (tool === "combine")
      await page
        .locator("#combine-files")
        .setInputFiles("docs/ux/public-synthetic-only/demo-a.pdf");
    else {
      await page
        .locator("#pdf-file")
        .setInputFiles("docs/ux/public-synthetic-only/demo-a.pdf");
      if (tool === "organize")
        await page
          .getByRole("button", { name: "Rotate page 1", exact: true })
          .click();
      else await page.getByLabel("Range 1 to", { exact: true }).fill("3");
    }
    const allTools = page.getByRole("button", {
      name: "← All tools",
      exact: true,
    });
    const dialog = page.getByRole("dialog", {
      name: "Leave this task?",
      exact: true,
    });
    for (const width of [1280, 390]) {
      await page.setViewportSize({ width, height: 844 });
      await allTools.click();
      await expect(dialog).toBeVisible();
      await expect(dialog.getByRole("button")).toHaveCount(2);
      await expect(
        dialog.getByRole("button", { name: "Keep editing", exact: true }),
      ).toBeFocused();
      await expect(dialog).toContainText(
        "Your original files will not be deleted.",
      );
      const centered = await dialog.evaluate((e) => {
        const r = e.getBoundingClientRect();
        return {
          x: Math.abs(r.left + r.width / 2 - innerWidth / 2),
          y: Math.abs(r.top + r.height / 2 - innerHeight / 2),
          fits:
            r.top >= 0 &&
            r.bottom <= innerHeight &&
            r.left >= 0 &&
            r.right <= innerWidth,
        };
      });
      expect(centered.x).toBeLessThan(2);
      expect(centered.y).toBeLessThan(2);
      expect(centered.fits).toBe(true);
      if (tool === "photos")
        await page.screenshot({
          path: info.outputPath(`ux8-leave-${info.project.name}-${width}.png`),
        });
      await dialog
        .getByRole("button", { name: "Keep editing", exact: true })
        .click();
      await expect(dialog).toHaveCount(0);
      await expect(allTools).toBeFocused();
      if (tool === "photos" || tool === "combine")
        await expect(page.locator(".photo-list>li")).toHaveCount(1);
      if (tool === "split")
        await expect(
          page.getByLabel("Range 1 to", { exact: true }),
        ).toHaveValue("3");
      if (tool === "organize")
        await expect(
          page.getByRole("button", { name: "Undo draft change", exact: true }),
        ).toBeEnabled();
      await allTools.click();
      await page.keyboard.press("Escape");
      await expect(dialog).toHaveCount(0);
    }
    await allTools.click();
    await dialog
      .getByRole("button", { name: "Discard task and leave", exact: true })
      .click();
    await expect(page.locator(".product-app")).toHaveAttribute(
      "data-screen",
      "home",
    );
    await expect(
      page.getByRole("button", { name: "Back to results", exact: true }),
    ).toHaveCount(0);
    await selectTool(page, name);
    await expect(page.locator(".photo-list>li")).toHaveCount(0);
    await expect(page.locator(".organize-task,.split-task")).toHaveCount(0);
  });
}
