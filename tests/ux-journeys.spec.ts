import { test, expect, type Page } from "@playwright/test";
import { PDFDocument } from "pdf-lib";
import { readFile } from "node:fs/promises";
const fixture = (name: string) => `docs/ux/public-synthetic-only/${name}`;
async function screen(page: Page, name: string) {
  for (const [width, height, suffix] of [
    [1280, 900, "desktop"],
    [390, 844, "phone"],
  ] as const) {
    await page.setViewportSize({ width, height });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    // The paper image must fit inside its sheet; a missing positioning rule
    // makes the lightbox look large while showing only a clipped corner.
    for (const sheet of await page.locator(".photo-sheet:visible").all()) {
      const bounds = await sheet.evaluate((e) => {
        const image = e.querySelector("img")!;
        const a = e.getBoundingClientRect(),
          b = image.getBoundingClientRect();
        return {
          inside:
            b.left >= a.left - 1 &&
            b.top >= a.top - 1 &&
            b.right <= a.right + 1 &&
            b.bottom <= a.bottom + 1,
        };
      });
      expect(bounds.inside).toBe(true);
    }
    for (const thumb of await page.locator(".organize-thumbnail:visible").all())
      await expect(thumb.locator("canvas")).toHaveCount(1);
    await page.screenshot({
      path: `docs/evidence/ux6-${name}-${suffix}.png`,
      fullPage: true,
    });
  }
  await page.setViewportSize({ width: 1280, height: 900 });
}
async function downloadedPages(page: Page) {
  const waiting = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PDF", exact: true }).click();
  return (
    await PDFDocument.load(await readFile((await (await waiting).path())!))
  ).getPageCount();
}
for (const tool of ["merge", "split", "organize", "images"] as const) {
  test(`${tool}: complete selection, workspace, result, download and fresh task journey`, async ({
    page,
  }, info) => {
    await page.goto("/");
    const name = {
      merge: "Combine PDFs",
      split: "Split a PDF",
      organize: "Organize pages",
      images: "Turn Photos into PDF",
    }[tool];
    await page.getByRole("button", { name, exact: true }).click();
    await screen(page, `${info.project.name}-${tool}-select`);
    if (tool === "merge") {
      await page.locator("#combine-files").setInputFiles(fixture("demo-a.pdf"));
      await expect(
        page.getByText("Add one more PDF to merge your files."),
      ).toBeVisible();
      await expect(
        page.getByRole("button", { name: "Apply combine", exact: true }),
      ).toBeDisabled();
      await page.locator("#combine-files").setInputFiles(fixture("demo-b.pdf"));
      await expect(page.locator(".merge-thumbnail img")).toHaveCount(2);
    } else if (tool === "images") {
      await page
        .locator("#photo-files")
        .setInputFiles([fixture("image-a.png"), fixture("image-b.png")]);
      const trigger = page.getByRole("button", {
        name: "Preview image 1",
        exact: true,
      });
      await expect(trigger).toBeEnabled();
      await trigger.click();
      const d = page.getByRole("dialog", { name: "Image page preview" });
      await expect(d).toContainText("1 / 2");
      await expect
        .poll(() =>
          d
            .locator(".photo-sheet")
            .evaluate((e) => e.getBoundingClientRect().width),
        )
        .toBeGreaterThan(400);
      await d.getByRole("button", { name: "Next page", exact: true }).click();
      await expect(d).toContainText("2 / 2");
      await screen(page, `${info.project.name}-image-lightbox`);
      await d
        .getByRole("button", { name: "Close preview", exact: true })
        .click();
      await expect(trigger).toBeFocused();
    } else {
      await page.locator("#pdf-file").setInputFiles(fixture("demo-a.pdf"));
      if (tool === "split") {
        await page
          .getByRole("combobox", { name: "Split mode", exact: true })
          .selectOption("fixed");
        await page.getByLabel("Pages per file", { exact: true }).fill("3");
      } else {
        await expect(page.locator(".source-context")).toContainText(
          "demo-a.pdf",
        );
        await expect(
          page.getByRole("button", { name: "Apply page changes", exact: true }),
        ).toBeDisabled();
        await expect(
          page.getByText(
            "Reorder, rotate or remove a page to create a new PDF.",
          ),
        ).toBeVisible();
        await page
          .getByRole("button", { name: "Delete page 6", exact: true })
          .click();
      }
    }
    await screen(page, `${info.project.name}-${tool}-workspace`);
    await page
      .getByRole("button", {
        name: {
          merge: "Apply combine",
          split: "Split PDF →",
          organize: "Apply page changes",
          images: "Convert to PDF →",
        }[tool],
        exact: true,
      })
      .click();
    await expect(page.locator(".product-app")).toHaveAttribute(
      "data-screen",
      "result",
      { timeout: 30000 },
    );
    await expect(
      page.getByRole("dialog", { name: "Processing PDF" }),
    ).toHaveCount(0);
    for (const selector of [
      ".combine-task",
      ".images-task",
      ".split-task",
      ".organize-task",
      ".preview",
    ])
      await expect(page.locator(selector)).not.toBeVisible();
    await screen(page, `${info.project.name}-${tool}-result`);
    if (tool === "split") {
      const waiting = page.waitForEvent("download");
      await page
        .getByRole("button", { name: "Download all PDFs (ZIP)", exact: true })
        .click();
      expect((await waiting).suggestedFilename()).toMatch(/\.zip$/);
    } else
      expect(await downloadedPages(page)).toBe(
        { merge: 9, organize: 5, images: 2 }[tool],
      );
    await page.getByRole("button", { name, exact: true }).click();
    await expect(page.locator(".photo-list > li")).toHaveCount(0);
    await expect(page.locator(".organize-task,.split-task")).toHaveCount(0);
    await expect(page.locator(".product-app")).toHaveAttribute(
      "data-screen",
      "task",
    );
  });
}

test("new file import and photo conversion keep independent task boundaries", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Combine PDFs", exact: true }).click();
  await page
    .locator("#combine-files")
    .setInputFiles([fixture("demo-a.pdf"), fixture("demo-b.pdf")]);
  await page
    .getByRole("button", { name: "Apply combine", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Download PDF", exact: true }),
  ).toBeVisible({ timeout: 30000 });
  await page.getByRole("button", { name: "Split a PDF", exact: true }).click();
  await page.locator("#pdf-file").setInputFiles(fixture("demo-b.pdf"));
  await expect(page.locator(".split-task")).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "Cancel task", exact: true }).click();
  await expect(page.locator(".product-app")).toHaveAttribute(
    "data-screen",
    "home",
  );
  await page
    .getByRole("button", { name: "Turn Photos into PDF", exact: true })
    .click();
  await page.locator("#photo-files").setInputFiles(fixture("image-a.png"));
  await expect(page.getByRole("checkbox", { name: /Replace/ })).toHaveCount(0);
  await page
    .getByRole("button", { name: "Convert to PDF →", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Download PDF", exact: true }),
  ).toBeVisible({ timeout: 30000 });
  expect(await downloadedPages(page)).toBe(1);
});

test("unsupported merge input can be removed, and cancel discards the draft safely", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Combine PDFs", exact: true }).click();
  await page.locator("#combine-files").setInputFiles([
    {
      name: "invalid.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("not a pdf"),
    },
  ]);
  await expect(page.locator(".photo-list [role=alert]")).toContainText(
    "Remove this input",
  );
  await page.getByRole("button", { name: "Remove PDF 1", exact: true }).click();
  await page.locator("#combine-files").setInputFiles(fixture("demo-a.pdf"));
  await page.getByRole("button", { name: "Cancel task", exact: true }).click();
  await expect(
    page.getByRole("dialog", {
      name: "Leave this task?",
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Discard task and leave", exact: true })
    .click();
  await expect(page.locator(".product-app")).toHaveAttribute(
    "data-screen",
    "home",
  );
  await page.getByRole("button", { name: "Combine PDFs", exact: true }).click();
  await expect(page.locator(".photo-list > li")).toHaveCount(0);
});
