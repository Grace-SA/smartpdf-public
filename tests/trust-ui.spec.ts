import { expect, test } from "@playwright/test";

test("homepage makes local processing and product identity clear", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", {
      name: "Simple PDF tools. Clear choices for your files.",
    }),
  ).toBeVisible();
  const trust = page.getByRole("region", {
    name: "Your privacy with Smart PDF",
  });
  await expect(trust.getByText("Local PDF tools")).toBeVisible();
  await expect(trust.getByText("Clearly marked cloud conversion")).toBeVisible();
  await expect(trust.getByText("Originals stay untouched")).toBeVisible();
  await expect(page.getByText("Proudly built in Australia")).toBeVisible();
  await expect(
    page.getByRole("link", { name: "hi@smartpdf.com.au" }),
  ).toHaveAttribute("href", "mailto:hi@smartpdf.com.au");
  await expect(
    page.getByRole("link", { name: /SmartWorks product/ }),
  ).toHaveAttribute("href", "https://smartworks.au");
});

test("tool pages put the local-processing assurance before file selection", async ({
  page,
}) => {
  await page.goto("/merge-pdf/");
  const banner = page.getByRole("note");
  await expect(banner.getByText("Private by design")).toBeVisible();
  await expect(banner).toContainText("No file or filename upload");
  await expect(
    page.getByText("Select PDF files or drop them here"),
  ).toBeVisible();
});

test("privacy and footer remain readable without horizontal overflow on phone", async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 760 });
  await page.goto("/");
  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport);
  await expect(
    page.locator(".trust-items").first().locator("article"),
  ).toHaveCount(3);
  await expect(page.locator(".site-footer")).toBeVisible();
});

test("upload help disappears when merge and image editing begins", async ({
  page,
}) => {
  for (const task of [
    {
      path: "/merge-pdf/",
      input: "#combine-files",
      file: "docs/ux/public-synthetic-only/demo-a.pdf",
      editor: ".combine-task",
    },
    {
      path: "/images-to-pdf/",
      input: "#photo-files",
      file: "docs/ux/public-synthetic-only/image-a.png",
      editor: ".photo-task.has-inputs",
    },
  ]) {
    await page.goto(task.path);
    await page.locator(task.input).setInputFiles(task.file);
    await expect(page.locator(task.editor)).toBeVisible();
    await expect(page.locator(".upload-support")).toHaveCount(0);
    const spacing = await page.evaluate((selector) => {
      const privacy = document.querySelector(".task-privacy-banner")!;
      const editor = document.querySelector(selector)!;
      return (
        editor.getBoundingClientRect().top -
        privacy.getBoundingClientRect().bottom
      );
    }, task.editor);
    expect(spacing).toBeGreaterThanOrEqual(12);
  }
});
