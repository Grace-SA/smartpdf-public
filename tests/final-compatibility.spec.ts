import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { PDFDocument } from "pdf-lib";
import { flatForm } from "../src/core/flat-form";
import { inspectAttachments } from "../src/combine/attachments";
import { inspectTags } from "../src/combine/tags";
test("the closing device batch combines retained tags, layers and empty form defaults", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await page.getByRole("button", { name: "Combine PDFs", exact: true }).click();
  await page
    .locator("#combine-files")
    .setInputFiles(
      ["indexed-artifact", "unconfigured-layer", "empty-form", "layer-off"].map(
        (n) => `tests/fixtures/combine/${n}.pdf`,
      ),
    );
  await page
    .getByRole("button", { name: "Apply combine", exact: true })
    .click();
  await expect(page.getByText("Page 1 of 4", { exact: true })).toBeVisible();
});
test("ordinary final coverage merges offline and saves original fields, attachments and incomplete tags", async ({
  page,
  context,
  browserName,
}, info) => {
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  // Playwright WebKit on Windows rejects FileReader even for an in-memory File
  // under network emulation. Real-device offline evidence is collected separately.
  await context.setOffline(browserName !== "webkit");
  const requests: string[] = [];
  page.on("request", (r) => {
    if (/^https?:/.test(r.url())) requests.push(r.url());
  });
  await page.getByRole("button", { name: "Combine PDFs", exact: true }).click();
  await page
    .locator("#combine-files")
    .setInputFiles(
      ["jpeg", "form", "attachment", "tags"].map(
        (n) => `tests/fixtures/combine/final-${n}.pdf`,
      ),
    );
  await page
    .getByRole("button", { name: "Apply combine", exact: true })
    .click();
  await expect(page.getByText("Page 1 of 4", { exact: true })).toBeVisible();
  await expect(page.locator(".canvas-host canvas")).toBeVisible();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Save PDF", exact: true }).click();
  const path = info.outputPath("synthetic-final.pdf");
  await (await downloaded).saveAs(path);
  const doc = await PDFDocument.load(await readFile(path));
  expect(flatForm(doc)!.widgets.size).toBe(1);
  expect(doc.getForm().getTextField("Example").getText()).toBe("Kept value");
  expect(inspectAttachments(doc).associated).toHaveLength(1);
  expect(inspectTags(doc)!.namespaces).toHaveLength(1);
  expect(requests).toEqual([]);
});
