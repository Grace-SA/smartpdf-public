import { test, expect } from "@playwright/test";
test("processing uses no native modal and releases inertness, focus and scrolling", async ({
  page,
}) => {
  await page.goto("/pdf-to-jpg/");
  await page.locator("#pdf-file").setInputFiles("tests/fixtures/m8-device.pdf");
  const convert = page.getByRole("button", {
    name: "Convert to JPG →",
    exact: true,
  });
  await expect(convert).toBeEnabled();
  await page.evaluate(() => {
    const original = HTMLCanvasElement.prototype.toBlob;
    HTMLCanvasElement.prototype.toBlob = function (callback, ...args) {
      setTimeout(() => original.call(this, callback, ...args), 1000);
    };
  });
  await convert.click();
  const dialog = page.getByRole("dialog", {
    name: "Processing PDF",
    exact: true,
  });
  await expect(dialog).toBeVisible();
  expect(
    await page.evaluate(() => document.querySelectorAll(":modal").length),
  ).toBe(0);
  await expect(page.locator("#root")).toHaveAttribute("inert", "");
  const cancel = dialog.getByRole("button", {
    name: "Cancel processing",
    exact: true,
  });
  await expect(cancel).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(cancel).toBeFocused();
  await expect(page.locator(".delivery")).toBeVisible();
  await expect(page.locator(".task-notice-backdrop,[inert]")).toHaveCount(0);
  expect(
    await page.evaluate(() => document.documentElement.style.overflow),
  ).toBe("");
  await page.getByRole("button", { name: /Choose new files/ }).click();
  const chooser = page.waitForEvent("filechooser");
  await page.locator("#pdf-file").click();
  await (await chooser).setFiles("tests/fixtures/m8-device.pdf");
  await expect(convert).toBeEnabled();
});
