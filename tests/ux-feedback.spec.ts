import { test, expect } from "@playwright/test";
import { PDFDocument, PDFName } from "pdf-lib";
import { readFile } from "node:fs/promises";
test("photo generated source, merge to five pages, split 2 2 1, delete a child page", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByRole("button", { name: "Turn Photos into PDF", exact: true })
    .click();
  await page.locator("#photo-files").setInputFiles({
    name: "local-image.jpg",
    mimeType: "image/jpeg",
    buffer: await readFile(
      process.env.SMARTWORKS_LOCAL_IMAGE || "tests/fixtures/photos/red.jpg",
    ),
  });
  await page
    .getByRole("button", { name: "Convert to PDF →", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Download PDF", exact: true }),
  ).toBeVisible({ timeout: 30000 });
  await expect(page.locator(".images-task")).not.toBeVisible();
  await page
    .getByRole("button", { name: "Continue editing Photos.pdf", exact: true })
    .click();
  await page
    .getByRole("dialog", { name: "Continue editing", exact: true })
    .getByRole("button", { name: "Merge PDF", exact: true })
    .click();
  await expect(page.locator(".photo-list > li")).toHaveCount(1);
  const d = await PDFDocument.create();
  for (let i = 0; i < 4; i++) d.addPage([300, 400]);
  await page.locator("#combine-files").setInputFiles({
    name: "four.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from(await d.save()),
  });
  await page
    .getByRole("button", { name: "Apply combine", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Download PDF", exact: true }),
  ).toBeVisible({ timeout: 30000 });
  await page.getByRole("button", { name: "Split a PDF", exact: true }).click();
  await page.getByRole("button", { name: "Use this PDF", exact: true }).click();
  await page.getByLabel("Range 1 to", { exact: true }).fill("2");
  for (const [n, from, to] of [
    [2, "3", "4"],
    [3, "5", "5"],
  ] as const) {
    await page
      .getByRole("button", { name: "+ Add range", exact: true })
      .click();
    await page.getByLabel(`Range ${n} from`, { exact: true }).fill(from);
    await page.getByLabel(`Range ${n} to`, { exact: true }).fill(to);
  }
  await page.getByRole("button", { name: "Split PDF →", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "3 PDFs ready to download",
      exact: true,
    }),
  ).toBeVisible({ timeout: 30000 });
  await page
    .getByRole("button", {
      name: "Continue editing Combined-part-01.pdf",
      exact: true,
    })
    .click();
  await page
    .getByRole("dialog", { name: "Continue editing", exact: true })
    .getByRole("button", { name: "Organize PDF", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Delete page 2", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Apply page changes", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Download PDF", exact: true }),
  ).toBeVisible({ timeout: 30000 });
  const dl = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PDF", exact: true }).click();
  expect(
    (
      await PDFDocument.load(await readFile((await (await dl).path())!))
    ).getPageCount(),
  ).toBe(1);
});

async function linkedInput() {
  const doc = await PDFDocument.create(),
    a = doc.addPage([300, 400]),
    b = doc.addPage([300, 400]);
  a.drawText("Link to page two", { x: 20, y: 320 });
  b.drawText("Page two", { x: 20, y: 320 });
  const ref = doc.context.register(
    doc.context.obj({
      Type: "Annot",
      Subtype: "Link",
      Rect: [20, 300, 100, 330],
      P: a.ref,
      Dest: [b.ref, "Fit"],
    }),
  );
  a.node.set(PDFName.of("Annots"), doc.context.obj([ref]));
  return {
    name: "linked-demo.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from(await doc.save()),
  };
}
for (const tool of ["Organize pages", "Split a PDF"])
  test(`${tool} shows blocked structural changes and explicit recovery`, async ({
    page,
  }) => {
    await page.goto("/");
    await page.getByRole("button", { name: tool, exact: true }).click();
    await page.locator("#pdf-file").setInputFiles(await linkedInput());
    if (tool === "Organize pages")
      await page
        .getByRole("button", { name: "Delete page 2", exact: true })
        .click();
    else
      await page
        .getByRole("combobox", { name: "Split mode", exact: true })
        .selectOption("each");
    const action = page.getByRole("button", {
      name: tool === "Organize pages" ? "Apply page changes" : "Split PDF →",
      exact: true,
    });
    await action.click();
    await expect(
      page.getByRole("dialog", { name: "PDF needs attention" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Download PDF", exact: true }),
    ).toHaveCount(0);
    await page
      .getByRole("button", { name: "Back to editing", exact: true })
      .click();
    await action.click();
    await page
      .getByRole("button", {
        name: "Allow these adjustments and create PDF",
        exact: true,
      })
      .click();
    await expect(
      page.getByRole("heading", {
        name:
          tool === "Organize pages"
            ? "Your PDF is ready"
            : "2 PDFs ready to download",
        exact: true,
      }),
    ).toBeVisible({ timeout: 30000 });
  });
test("lightbox fit page, keyboard page navigation, zoom and focus restoration", async ({
  page,
}, info) => {
  await page.goto("/");
  await page
    .getByRole("button", { name: "Organize pages", exact: true })
    .click();
  await page
    .locator("#pdf-file")
    .setInputFiles("docs/ux/public-synthetic-only/demo-a.pdf");
  const trigger = page.getByRole("button", {
    name: "Enlarge original page 3",
    exact: true,
  });
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "Enlarged selected page" });
  await expect(dialog.locator("canvas")).toHaveCount(1);
  await expect(
    dialog.getByRole("combobox", { name: "Zoom", exact: true }),
  ).toHaveValue("1");
  await dialog.getByRole("button", { name: "Next page", exact: true }).click();
  await expect(dialog.locator("canvas")).toHaveAttribute(
    "aria-label",
    /Original page 4,/,
  );
  await dialog.press("ArrowLeft");
  await expect(dialog.locator("canvas")).toHaveAttribute(
    "aria-label",
    /Original page 3,/,
  );
  await dialog
    .getByRole("combobox", { name: "Zoom", exact: true })
    .selectOption("2");
  await expect
    .poll(() =>
      dialog
        .locator(".page-detail-canvas")
        .evaluate((e) => e.scrollWidth > e.clientWidth),
    )
    .toBe(true);
  await dialog
    .getByRole("combobox", { name: "Zoom", exact: true })
    .selectOption("0");
  await expect
    .poll(() =>
      dialog
        .locator(".page-detail-canvas")
        .evaluate((e) => e.scrollHeight <= e.clientHeight + 2),
    )
    .toBe(true);
  await page.screenshot({
    path: `docs/evidence/ux4-${info.project.name}-preview.png`,
  });
  await dialog.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await expect(
    page.getByRole("button", { name: "Apply page changes", exact: true }),
  ).toBeDisabled();
});
test("single image chooser retains all supported image types and one-page preview hides navigation", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByRole("button", { name: "Turn Photos into PDF", exact: true })
    .click();
  await expect(page.locator(".images-task input[type=file]")).toHaveCount(1);
  await expect(page.locator("#photo-files")).toHaveAttribute(
    "accept",
    "image/*,.heic,.heif",
  );
  await page
    .locator("#photo-files")
    .setInputFiles("tests/fixtures/photos/red.jpg");
  await page
    .getByRole("button", { name: "Convert to PDF →", exact: true })
    .click();
  await page.locator(".result-more-tools summary").click();
  await page
    .locator(".result-more-tools")
    .getByRole("button", { name: "Organize PDF", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Enlarge original page 1", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Next page", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Previous page", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Close preview", exact: true })
    .click();
});

test("one chooser processes JPEG PNG and HEIC together", async ({ page }) => {
  await page.goto("/");
  await page
    .getByRole("button", { name: "Turn Photos into PDF", exact: true })
    .click();
  await page
    .locator("#photo-files")
    .setInputFiles([
      "tests/fixtures/photos/red.jpg",
      "docs/ux/public-synthetic-only/image-a.png",
      "tests/fixtures/photos/synthetic.heic",
    ]);
  await page
    .getByRole("button", { name: "Convert to PDF →", exact: true })
    .click();
  const dl = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PDF", exact: true }).click();
  expect(
    (
      await PDFDocument.load(await readFile((await (await dl).path())!))
    ).getPageCount(),
  ).toBe(3);
});
test("phone preview fits page and closes without changing split selection", async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Split a PDF", exact: true }).click();
  await page
    .locator("#pdf-file")
    .setInputFiles("docs/ux/public-synthetic-only/demo-a.pdf");
  await page
    .getByRole("button", { name: "Preview page 2", exact: true })
    .click();
  const d = page.getByRole("dialog", { name: "Enlarged selected page" });
  await d
    .getByRole("combobox", { name: "Zoom", exact: true })
    .selectOption("0");
  await expect(d.locator("canvas")).toHaveCount(1);
  await expect
    .poll(() =>
      d
        .locator(".page-detail-canvas")
        .evaluate(
          (e) =>
            e.scrollWidth <= e.clientWidth + 2 &&
            e.scrollHeight <= e.clientHeight + 2,
        ),
    )
    .toBe(true);
  await expect(
    d.getByRole("button", { name: "Close preview", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: `docs/evidence/ux4-${info.project.name}-phone-preview.png`,
  });
  await d.getByRole("button", { name: "Close preview", exact: true }).click();
  await expect(page.getByLabel("Range 1 to", { exact: true })).toHaveValue("6");
});
