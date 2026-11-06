import { test, expect } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import { openTools } from "./navigation";

test("publication includes Word, Excel and Unlock without Protect entry points", async ({
  page,
}) => {
  expect(existsSync("dist/protect-pdf/index.html")).toBe(false);
  expect(readFileSync("dist/sitemap.xml", "utf8")).not.toContain("protect-pdf");
  expect(existsSync("dist/excel-to-pdf/index.html")).toBe(true);
  expect(readFileSync("dist/sitemap.xml", "utf8")).toContain("excel-to-pdf");
  for (const path of [
    "/",
    "/word-to-pdf/",
    "/excel-to-pdf/",
    "/unlock-pdf/",
    "/protect-pdf/",
  ]) {
    await page.goto(path);
    await openTools(page);
    await expect(
      page.locator('.tool-nav a[href="/word-to-pdf/"]'),
    ).toBeVisible();
    await expect(
      page.locator('.tool-nav a[href="/unlock-pdf/"]'),
    ).toBeVisible();
    await expect(
      page.locator('.tool-nav a[href="/excel-to-pdf/"]'),
    ).toBeVisible();
    await expect(page.locator('a[href="/protect-pdf/"]')).toHaveCount(0);
    await expect(
      page.getByRole("heading", { name: "Protect PDF", exact: true }),
    ).toHaveCount(0);
    await page.locator(".tools-toggle").click();
    if (path === "/word-to-pdf/") {
      await expect(page.locator("#word-file")).toBeAttached();
      await expect(
        page.getByText("Upload starts only when you convert.", {
          exact: false,
        }),
      ).toBeVisible();
    }
    if (path === "/excel-to-pdf/")
      await expect(page.locator("#excel-file")).toBeAttached();
    if (path === "/unlock-pdf/")
      await expect(
        page.getByRole("heading", { name: "Unlock PDF", exact: true }),
      ).toBeVisible();
  }
});
