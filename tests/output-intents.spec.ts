import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { PDFDocument } from "pdf-lib";
import { outputIntents } from "../src/combine/output-intents";
test("profiled PDFs save their colour settings offline and incompatible additions retain the result", async ({
  page,
  context,
  browserName,
}, info) => {
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  // Playwright WebKit on Windows rejects FileReader even for an in-memory File
  // under network emulation. Real-device offline evidence is collected separately.
  await context.setOffline(browserName !== "webkit");
  await page.getByRole("button", { name: "Combine PDFs", exact: true }).click();
  await page
    .locator("#combine-files")
    .setInputFiles([
      "tests/fixtures/combine/final-color.pdf",
      "tests/fixtures/combine/final-color.pdf",
    ]);
  await page
    .getByRole("button", { name: "Apply combine", exact: true })
    .click();
  await expect(page.getByText("Page 1 of 2", { exact: true })).toBeVisible();
  const promise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Save PDF", exact: true }).click();
  const path = info.outputPath("profiled.pdf");
  await (await promise).saveAs(path);
  const source = await PDFDocument.load(
      await readFile("tests/fixtures/combine/final-color.pdf"),
    ),
    output = await PDFDocument.load(await readFile(path));
  expect(outputIntents(source)!.identity).toBe(outputIntents(output)!.identity);
  await page.getByRole("button", { name: "Combine PDFs", exact: true }).click();
  await page
    .locator("#combine-files")
    .setInputFiles("tests/fixtures/combine/a.pdf");
  await page
    .getByRole("button", { name: "Apply combine", exact: true })
    .click();
  await expect(
    page.getByRole("alert").filter({ hasText: /colour/ }),
  ).toBeVisible();
  await expect(page.getByText("Page 1 of 2", { exact: true })).toBeVisible();
});
