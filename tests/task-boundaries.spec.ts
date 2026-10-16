import { selectTool } from "./navigation";
import { test, expect, type Page } from "@playwright/test";
import { PDFDocument } from "pdf-lib";
import { readFile } from "node:fs/promises";
const root = "docs/ux/public-synthetic-only/";
async function downloadPages(page: Page, count: number) {
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PDF", exact: true }).click();
  const doc = await PDFDocument.load(
    await readFile((await (await pending).path())!),
  );
  expect(doc.getPageCount()).toBe(count);
}
for (const width of [390, 1280])
  for (const tool of ["images", "merge", "organize", "split"] as const) {
    test(`${tool} ${width}: completion only offers download and a fresh-task return`, async ({
      page,
    }, info) => {
      await page.setViewportSize({ width, height: 844 });
      const external: string[] = [];
      page.on("request", (request) => {
        if (
          /^https?:/.test(request.url()) &&
          new URL(request.url()).origin !==
            new URL(String(info.project.use.baseURL)).origin
        )
          external.push(request.url());
      });
      await page.goto("/");
      const title = {
        images: "Turn Photos into PDF",
        merge: "Combine PDFs",
        organize: "Organize pages",
        split: "Split a PDF",
      }[tool];
      await selectTool(page, title);
      if (tool === "images")
        await page
          .locator("#photo-files")
          .setInputFiles([root + "image-a.png", root + "image-b.png"]);
      else if (tool === "merge")
        await page
          .locator("#combine-files")
          .setInputFiles([root + "demo-a.pdf", root + "demo-b.pdf"]);
      else await page.locator("#pdf-file").setInputFiles(root + "demo-a.pdf");
      if (tool === "organize") {
        await page
          .getByRole("button", { name: "Delete page 6", exact: true })
          .click();
        await page
          .getByRole("button", { name: "Undo draft change", exact: true })
          .click();
        await expect(
          page.getByRole("button", { name: "Delete page 6", exact: true }),
        ).toBeVisible();
        await page
          .getByRole("button", { name: "Redo draft change", exact: true })
          .click();
      }
      if (tool === "split")
        await page.getByLabel("Range 1 to", { exact: true }).fill("2");
      const action = {
        images: "Convert to PDF →",
        merge: "Apply combine",
        organize: "Apply page changes",
        split: "Split PDF →",
      }[tool];
      await page.getByRole("button", { name: action, exact: true }).click();
      await expect(page.locator(".product-app")).toHaveAttribute(
        "data-screen",
        "result",
      );
      const result = page.getByRole("region", { name: "Completed task" });
      await expect(result.getByRole("heading", { level: 1 })).toBeFocused();
      await expect(result.locator(".output-summary")).toContainText("pages");
      await expect(result.getByRole("button")).toHaveCount(2);
      await expect(
        result.getByRole("button", { name: "Download PDF", exact: true }),
      ).toBeInViewport();
      await expect(
        page.locator(
          ".result-files, .result-more-tools, .session-history, .preview",
        ),
      ).toHaveCount(0);
      await expect(
        page.getByRole("button", { name: action, exact: true }),
      ).not.toBeVisible();
      await page.screenshot({
        path: info.outputPath(`ux12-${info.project.name}-${tool}-${width}.png`),
        fullPage: true,
      });
      const count = { images: 2, merge: 9, organize: 5, split: 2 }[tool];
      await downloadPages(page, count);
      await downloadPages(page, count); // Repeat download keeps the same completed output.
      expect(external).toEqual([]);
      await result
        .getByRole("button", { name: "Choose new files", exact: true })
        .click();
      await expect(page.locator(".product-app")).toHaveAttribute(
        "data-screen",
        "task",
      );
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(
        page.locator(
          ".photo-list > li, .split-task, .organize-task, .delivery",
        ),
      ).toHaveCount(0);
      await expect(
        page.locator(
          tool === "images"
            ? "#photo-files"
            : tool === "merge"
              ? "#combine-files"
              : "#pdf-file",
        ),
      ).toHaveValue("");
    });
  }
test("multiple split results download together; navigation starts a clean task", async ({
  page,
}, info) => {
  await page.goto("/");
  await selectTool(page, "Split a PDF");
  await page.locator("#pdf-file").setInputFiles(root + "demo-a.pdf");
  await page
    .getByRole("combobox", { name: "Split mode", exact: true })
    .selectOption("fixed");
  await page.getByRole("button", { name: "Split PDF →", exact: true }).click();
  await expect(page.locator(".output-summary")).toContainText("3 PDF files");
  await page.screenshot({
    path: info.outputPath(`ux12-${info.project.name}-zip.png`),
    fullPage: true,
  });
  await page.evaluate(() => {
    const original = URL.createObjectURL;
    let failed = false;
    URL.createObjectURL = (blob: Blob | MediaSource) => {
      if (blob instanceof Blob && blob.type === "application/zip" && !failed) {
        failed = true;
        throw new Error("Synthetic download failure");
      }
      return original(blob);
    };
  });
  await page
    .getByRole("button", { name: "Download all PDFs (ZIP)", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "Your results are still here",
  );
  await expect(
    page.getByRole("button", { name: "Download all PDFs (ZIP)", exact: true }),
  ).toBeEnabled();
  const pending = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download all PDFs (ZIP)", exact: true })
    .click();
  const zip = await readFile((await (await pending).path())!);
  let offset = 0;
  const pages: number[] = [];
  const names: string[] = [];
  while (zip.readUInt32LE(offset) === 0x04034b50) {
    expect(zip.readUInt16LE(offset + 8)).toBe(0);
    const size = zip.readUInt32LE(offset + 18),
      nameLength = zip.readUInt16LE(offset + 26),
      extra = zip.readUInt16LE(offset + 28);
    names.push(zip.subarray(offset + 30, offset + 30 + nameLength).toString());
    const start = offset + 30 + nameLength + extra;
    pages.push(
      (
        await PDFDocument.load(zip.subarray(start, start + size))
      ).getPageCount(),
    );
    offset = start + size;
  }
  expect(pages).toEqual([2, 2, 2]);
  expect(new Set(names).size).toBe(3);
  await selectTool(page, "Organize pages");
  await expect(page.locator("#pdf-file")).toHaveValue("");
  await expect(page.locator(".organize-task, .delivery")).toHaveCount(0);
});

test("cancel a dirty task leaves once without a second confirmation", async ({
  page,
}) => {
  await page.goto("/");
  await selectTool(page, "Organize pages");
  await page.locator("#pdf-file").setInputFiles(root + "demo-a.pdf");
  await page
    .getByRole("button", { name: "Delete page 2", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Cancel page changes", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Discard task and leave", exact: true })
    .click();
  await expect(page.locator(".product-app")).toHaveAttribute(
    "data-screen",
    "home",
  );
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("long result names, ZIP summary and compact screens preserve download hierarchy", async ({
  page,
}, info) => {
  await page.goto("/");
  await expect(page.locator(".tool-home")).toBeVisible();
  await page.screenshot({
    path: info.outputPath(`ux12-${info.project.name}-home.png`),
    fullPage: true,
  });
  await selectTool(page, "Split a PDF");
  await page.locator("#pdf-file").setInputFiles({
    name: "Quarterly_Report_with_a_very_long_descriptive_filename_for_download_layout_and_mobile_review.pdf",
    mimeType: "application/pdf",
    buffer: await readFile(root + "demo-a.pdf"),
  });
  await page.getByLabel("Range 1 to", { exact: true }).fill("2");
  await page.getByRole("button", { name: "Split PDF →", exact: true }).click();
  await expect(page.locator(".output-summary strong")).toContainText(
    "Quarterly_Report",
  );
  for (const [width, height] of [
    [320, 740],
    [768, 1024],
    [844, 390],
    [1440, 900],
  ] as const) {
    await page.setViewportSize({ width, height });
    await expect(page.locator(".download-primary")).toBeVisible();
    const overflow = await page.evaluate(() => ({
      width: innerWidth,
      scroll: document.documentElement.scrollWidth,
      offenders: Array.from(document.querySelectorAll("body *"))
        .filter((e) => e.getBoundingClientRect().right > innerWidth + 1)
        .map((e) => e.className)
        .slice(0, 15),
    }));
    expect(overflow.scroll, JSON.stringify(overflow)).toBeLessThanOrEqual(
      overflow.width,
    );
    for (const navButton of await page.locator(".tool-nav a:visible").all()) {
      const bounds = (await navButton.boundingBox())!;
      expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
    }
    const button = (await page.locator(".download-primary").boundingBox())!;
    expect(Math.abs(button.x + button.width / 2 - width / 2)).toBeLessThan(2);
    expect(button.height).toBeGreaterThanOrEqual(44);
    await page.screenshot({
      path: info.outputPath(`ux12-${info.project.name}-long-${width}.png`),
      fullPage: true,
    });
  }
  await page.evaluate(() => {
    const original = URL.createObjectURL;
    let fail = true;
    URL.createObjectURL = (blob: Blob | MediaSource) => {
      if (fail && blob instanceof Blob && blob.type === "application/pdf") {
        fail = false;
        throw Error("Synthetic failure");
      }
      return original(blob);
    };
  });
  await page.getByRole("button", { name: "Download PDF", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Your result is still here",
  );
  await downloadPages(page, 2);
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.locator(".download-feedback [role=status]")).toContainText(
    "Download started",
  );
});
