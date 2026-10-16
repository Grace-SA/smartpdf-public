import { test, expect } from "@playwright/test";
import { PDFDocument } from "pdf-lib";
import { readFile } from "node:fs/promises";

test("results preview is read-only, tool changes require a file choice, continuation targets the chosen child", async ({
  page,
}, info) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Split a PDF", exact: true }).click();
  await page
    .locator("#pdf-file")
    .setInputFiles("docs/ux/public-synthetic-only/demo-a.pdf");
  await page
    .getByRole("combobox", { name: "Split mode", exact: true })
    .selectOption("fixed");
  await page.getByLabel("Pages per file", { exact: true }).fill("2");
  await page.getByRole("button", { name: "Split PDF →", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "3 PDFs ready to download",
      exact: true,
    }),
  ).toBeVisible({ timeout: 30000 });
  await page.screenshot({
    path: `docs/evidence/ux5-${info.project.name}-results.png`,
    fullPage: true,
  });
  const trigger = page.getByRole("button", {
    name: "Preview result demo-a-part-02.pdf",
    exact: true,
  });
  await trigger.click();
  const preview = page.getByRole("dialog", { name: "Enlarged selected page" });
  await expect(preview.locator("canvas")).toHaveCount(1);
  await expect(preview).toContainText("1 / 2");
  await preview.getByRole("button", { name: "Next page", exact: true }).click();
  await expect(preview).toContainText("2 / 2");
  await preview
    .getByRole("button", { name: "Close preview", exact: true })
    .click();
  await expect(trigger).toBeFocused();
  await expect(page.locator(".product-app")).toHaveAttribute(
    "data-screen",
    "result",
  );
  await expect(page.locator(".preview")).not.toBeVisible();
  await page
    .getByRole("button", { name: "Organize pages", exact: true })
    .click();
  await expect(page.locator(".organize-task")).toHaveCount(0);
  await expect(page.locator(".reuse-file")).toContainText("demo-a.pdf");
  await expect(
    page.getByRole("button", { name: "Use this PDF", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Back to results", exact: true })
    .click();
  await page
    .getByRole("button", {
      name: "Continue editing demo-a-part-02.pdf",
      exact: true,
    })
    .click();
  await page
    .getByRole("dialog", { name: "Continue editing", exact: true })
    .getByRole("button", { name: "Organize PDF", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Delete page 2", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Delete page 3", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Delete page 2", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Apply page changes", exact: true })
    .click();
  const waiting = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PDF", exact: true }).click();
  const doc = await PDFDocument.load(
    await readFile((await (await waiting).path())!),
  );
  expect(doc.getPageCount()).toBe(1);
});

test("merge preview renders actual pages at readable width and preserves the merge draft", async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto("/");
  await page.getByRole("button", { name: "Combine PDFs", exact: true }).click();
  await page
    .locator("#combine-files")
    .setInputFiles([
      "docs/ux/public-synthetic-only/demo-a.pdf",
      "docs/ux/public-synthetic-only/demo-b.pdf",
    ]);
  await expect(page.locator(".merge-thumbnail img")).toHaveCount(2);
  await page
    .getByRole("button", { name: "Preview PDF 1", exact: true })
    .click();
  const d = page.getByRole("dialog", { name: "Enlarged selected page" });
  await expect(d.locator("canvas")).toHaveCount(1);
  await expect(d).toContainText("1 / 6");
  await expect
    .poll(() =>
      d.locator("canvas").evaluate((e) => e.getBoundingClientRect().width),
    )
    .toBeGreaterThan(1200);
  await d.getByRole("button", { name: "Next page", exact: true }).click();
  await expect(d.locator("canvas")).toHaveAttribute(
    "aria-label",
    /Original page 2,/,
  );
  await page.screenshot({
    path: `docs/evidence/ux5-${info.project.name}-preview.png`,
  });
  await d.getByRole("button", { name: "Close preview", exact: true }).click();
  await expect(page.locator(".photo-list > li")).toHaveCount(2);
  await page
    .getByRole("button", { name: "Apply combine", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Download PDF", exact: true }),
  ).toBeVisible({ timeout: 30000 });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator(".combine-task")).not.toBeVisible();
  await page.screenshot({
    path: `docs/evidence/ux5-${info.project.name}-phone-results.png`,
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "Combine PDFs", exact: true }).click();
  await expect(page.locator(".photo-list > li")).toHaveCount(0);
});
