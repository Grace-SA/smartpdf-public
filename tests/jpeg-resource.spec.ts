import { test, expect } from "@playwright/test";
import { jpegResourceFixture } from "./jpeg-resource-fixture";
import { makeFixture } from "./fixtures";

test("encoded JPEG limits reject understated wrapped images and preserve the current document", async ({
  page,
  context,
  browserName,
}) => {
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await context.setOffline(browserName !== "webkit");
  await page.locator("#pdf-file").setInputFiles({
    name: "retained.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from(await makeFixture()),
  });
  await expect(page.getByText("Page 1 of 2", { exact: true })).toBeVisible();
  for (const wrapped of [false, true]) {
    await page.locator("#pdf-file").setInputFiles({
      name: "oversized.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from(await jpegResourceFixture(wrapped)),
    });
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "retained.pdf" }),
    ).toBeVisible();
    await expect(page.getByText("Page 1 of 2", { exact: true })).toBeVisible();
    await expect(page.locator("#pdf-file")).toBeEnabled();
  }
  await page.getByRole("button", { name: "Combine PDFs", exact: true }).click();
  await page.locator("#combine-files").setInputFiles({
    name: "oversized.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from(await jpegResourceFixture(true)),
  });
  await expect(
    page.getByRole("button", { name: "Apply combine", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("heading", { name: "retained.pdf" }),
  ).toBeVisible();
});
