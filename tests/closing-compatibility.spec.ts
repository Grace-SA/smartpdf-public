import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { PDFDocument, PDFDict, PDFName, PDFBool } from "pdf-lib";
import { emptyForm, formIdentity } from "../src/core/empty-form";

test("empty-form export saves offline; rejecting an interactive form retains the valid queue", async ({
  page,
  context,
  browserName,
}) => {
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await page.getByRole("button", { name: "Combine PDFs", exact: true }).click();
  // Playwright WebKit on Windows rejects FileReader even for an in-memory File
  // under network emulation. Real-device offline evidence is collected separately.
  await context.setOffline(browserName !== "webkit");
  await page
    .locator("#combine-files")
    .setInputFiles([
      "tests/fixtures/combine/empty-form.pdf",
      "tests/fixtures/combine/a.pdf",
      "tests/fixtures/form.pdf",
    ]);
  await expect(page.locator(".photo-list li")).toHaveCount(3);
  await expect(
    page.locator(".photo-list li").last().getByRole("alert"),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Apply combine", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Remove PDF 3", exact: true }).click();
  await expect(page.locator(".photo-list li")).toHaveCount(2);
  await page
    .getByRole("button", { name: "Apply combine", exact: true })
    .click();
  await expect(page.getByText("Page 1 of 3", { exact: true })).toBeVisible();
  const downloading = page.waitForEvent("download");
  await page.getByRole("button", { name: "Save PDF", exact: true }).click();
  const download = await downloading;
  const source = await PDFDocument.load(
    await readFile("tests/fixtures/combine/empty-form.pdf"),
  );
  const output = await PDFDocument.load(
    await readFile((await download.path())!),
  );
  expect(formIdentity(output, emptyForm(output)!)).toBe(
    formIdentity(source, emptyForm(source)!),
  );
});

test("optional missing tag indexes merge and save offline without discarding the source tree", async ({
  page,
  context,
  browserName,
}) => {
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await page.getByRole("button", { name: "Combine PDFs", exact: true }).click();
  // Playwright WebKit on Windows rejects FileReader even for an in-memory File
  // under network emulation. Real-device offline evidence is collected separately.
  await context.setOffline(browserName !== "webkit");
  await page
    .locator("#combine-files")
    .setInputFiles([
      "tests/fixtures/combine/optional-tag-indexes.pdf",
      "tests/fixtures/combine/a.pdf",
    ]);
  await page
    .getByRole("button", { name: "Apply combine", exact: true })
    .click();
  await expect(page.getByText("Page 1 of 3", { exact: true })).toBeVisible();
  const downloading = page.waitForEvent("download");
  await page.getByRole("button", { name: "Save PDF", exact: true }).click();
  const download = await downloading;
  const doc = await PDFDocument.load(await readFile((await download.path())!));
  expect(
    doc.catalog.lookup(PDFName.of("StructTreeRoot"), PDFDict),
  ).toBeTruthy();
  expect(
    doc.catalog
      .lookup(PDFName.of("MarkInfo"), PDFDict)
      .get(PDFName.of("Suspects")),
  ).toBe(PDFBool.True);
});
