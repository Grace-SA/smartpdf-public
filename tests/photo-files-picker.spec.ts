import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";
test("manual-only phone check opens the new Files picker without rerunning automatic checks", async ({
  page,
}) => {
  await page.goto("/__heic/check");
  await page
    .getByRole("button", { name: "只补测 Files 选取（无需重跑自动测试）" })
    .click({ timeout: 30000 });
  await expect(page.locator("#manual")).toBeVisible();
  await expect(
    page.frameLocator("#app").locator("#photo-browse-files"),
  ).toBeVisible();
  const report = JSON.parse((await page.locator("#results").textContent())!);
  expect(report.manualOnly).toBe(true);
  expect(report.checks).toEqual([]);
  expect(report.error).toBeUndefined();
});
test("Files picker accepts original HEIC with unknown MIME and still rejects non-images", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await page
    .getByRole("button", { name: "Turn Photos into PDF", exact: true })
    .click();
  const input = page.locator("#photo-browse-files");
  expect(await input.getAttribute("accept")).toBeNull();
  await input.setInputFiles({
    name: "original.heic",
    mimeType: "application/octet-stream",
    buffer: await readFile("tests/fixtures/photos/synthetic.heic"),
  });
  await expect(page.locator(".photo-list li")).toHaveCount(1);
  await expect(
    page.getByRole("button", { name: "Apply photos", exact: true }),
  ).toBeEnabled();
  await input.setInputFiles({
    name: "not-an-image.heic",
    mimeType: "image/heic",
    buffer: Buffer.from("not an image"),
  });
  await expect(page.locator(".photo-list [role=alert]")).toContainText(
    "Choose a complete",
  );
  await expect(
    page.getByRole("button", { name: "Apply photos", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Remove image 2", exact: true })
    .click();
  await page.getByRole("button", { name: "Apply photos", exact: true }).click();
  await expect(page.getByText("Page 1 of 1", { exact: true })).toBeVisible();
});
