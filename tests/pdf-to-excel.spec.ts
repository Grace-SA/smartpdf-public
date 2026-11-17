import { test, expect } from "@playwright/test";
import path from "node:path";
const fixtures = process.env.PDF_EXCEL_FIXTURES || ".pdf-excel-fixtures";
test.beforeEach(async ({ page }) => {
  await page.goto("/pdf-to-excel/");
  await expect(
    page.getByRole("heading", { name: "PDF to Excel", exact: true }),
  ).toBeVisible();
  await expect(page.locator("#header-tools")).toBeHidden();
  expect((await page.locator("header").boundingBox())!.height).toBeLessThan(
    110,
  );
});
for (const name of [
  "ruled",
  "borderless",
  "merged",
  "chinese",
  "scan",
  "mixed",
])
  test(`real conversion ${name}`, async ({ page }, testInfo) => {
    let uploads = 0;
    page.on("request", (r) => {
      if (r.method() === "POST" && r.url().includes("/api/pdf-to-excel/jobs"))
        uploads++;
    });
    await page
      .locator("input[type=file]")
      .setInputFiles(path.join(fixtures, name + ".pdf"));
    expect(uploads).toBe(0);
    await page
      .getByRole("button", { name: "Upload and convert", exact: true })
      .click();
    await expect(
      page.getByRole("link", { name: "Download Excel", exact: true }),
    ).toBeVisible();
    expect(uploads).toBe(1);
    await expect(page.getByRole("table")).toContainText(
      name === "chinese" ? "测试产品" : "Widget A",
    );
    const download = page.waitForEvent("download");
    await page
      .getByRole("link", { name: "Download Excel", exact: true })
      .click();
    const d = await download;
    expect(d.suggestedFilename()).toBe(name + ".xlsx");
    await d.saveAs(testInfo.outputPath(name + ".xlsx"));
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    if (name === "ruled")
      await page.screenshot({
        path: testInfo.outputPath("result.png"),
        fullPage: true,
      });
    await page.getByRole("button", { name: "Convert another PDF" }).click();
    await expect(
      page.getByRole("heading", { name: "Select a PDF" }),
    ).toBeVisible();
  });
test("page selection and single worksheet", async ({ page }) => {
  await page
    .locator("input[type=file]")
    .setInputFiles(path.join(fixtures, "multipage.pdf"));
  await page.getByLabel("Pages", { exact: true }).fill("2");
  await page.getByLabel("Worksheet layout").selectOption("single");
  await page
    .getByRole("button", { name: "Upload and convert", exact: true })
    .click();
  await expect(
    page.getByRole("link", { name: "Download Excel", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("table")).toContainText("00123");
  await expect(page.getByLabel("Table preview")).toContainText("Page 2");
});
for (const layout of ["tables", "single"])
  test(`native form preserves fields and checkbox states: ${layout}`, async ({
    page,
  }, testInfo) => {
    await page
      .locator("input[type=file]")
      .setInputFiles(path.join(fixtures, "native-form.pdf"));
    await page.getByLabel("Worksheet layout").selectOption(layout);
    await page
      .getByRole("button", { name: "Upload and convert", exact: true })
      .click();
    const link = page.getByRole("link", {
      name: "Download Excel",
      exact: true,
    });
    await expect(link).toBeVisible();
    await expect(page.locator(".px-result")).toContainText(
      `2 form pages · ${layout === "single" ? "1 worksheet" : "2 worksheets"}`,
    );
    await expect(page.getByRole("table")).toContainText(
      "Synthetic application 1",
    );
    await expect(page.getByRole("table")).toContainText("☒ Choice 1");
    await expect(page.getByRole("table")).toContainText("☐ Choice 2");
    await expect(page.getByRole("table")).toContainText("00017");
    await expect(page.getByRole("table")).toContainText("=1+1");
    await page.getByLabel("Form preview").selectOption("1");
    await expect(page.getByRole("table")).toContainText(
      "Synthetic application 2",
    );
    const download = page.waitForEvent("download");
    await link.click();
    await (
      await download
    ).saveAs(testInfo.outputPath(`native-form-${layout}.xlsx`));
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: testInfo.outputPath(`native-form-${layout}.png`),
      fullPage: true,
    });
  });
test("invalid file and range recover without upload", async ({ page }) => {
  await page.locator("input[type=file]").setInputFiles({
    name: "empty.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.alloc(0),
  });
  await expect(page.getByRole("alert")).toContainText("empty");
  await page
    .locator("input[type=file]")
    .setInputFiles(path.join(fixtures, "ruled.pdf"));
  await page.getByLabel("Pages", { exact: true }).fill("0");
  await expect(
    page.getByRole("button", { name: "Upload and convert", exact: true }),
  ).toBeDisabled();
  await page.getByLabel("Pages", { exact: true }).fill("1");
  await expect(
    page.getByRole("button", { name: "Upload and convert", exact: true }),
  ).toBeEnabled();
});
test("encrypted input reports failure and permits retry", async ({ page }) => {
  await page
    .locator("input[type=file]")
    .setInputFiles(path.join(fixtures, "encrypted.pdf"));
  await page
    .getByRole("button", { name: "Upload and convert", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("Unlock");
  await expect(
    page.getByRole("button", { name: "Upload and convert", exact: true }),
  ).toBeEnabled();
});
test("cancel ignores a delayed response", async ({ page }) => {
  await page.route("**/api/pdf-to-excel/jobs?**", async (route) => {
    await new Promise((r) => setTimeout(r, 1500));
    await route
      .fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({ id: "a".repeat(48), state: "queued" }),
      })
      .catch(() => {});
  });
  await page
    .locator("input[type=file]")
    .setInputFiles(path.join(fixtures, "ruled.pdf"));
  await page
    .getByRole("button", { name: "Upload and convert", exact: true })
    .click();
  await page.getByRole("button", { name: "Cancel conversion" }).click();
  await expect(page.getByRole("alert")).toContainText("cancelled");
  await expect(
    page.getByRole("link", { name: "Download Excel", exact: true }),
  ).toHaveCount(0);
});
test("connection failure recovers", async ({ page }) => {
  await page.route("**/api/pdf-to-excel/session", (route) => route.abort());
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Retry connection" }),
  ).toBeVisible();
  await page.unroute("**/api/pdf-to-excel/session");
  await page.getByRole("button", { name: "Retry connection" }).click();
  await page
    .locator("input[type=file]")
    .setInputFiles(path.join(fixtures, "ruled.pdf"));
  await expect(
    page.getByRole("button", { name: "Upload and convert", exact: true }),
  ).toBeEnabled();
});

test("leaving a selected file can be cancelled or confirmed", async ({
  page,
}) => {
  await page
    .locator("input[type=file]")
    .setInputFiles(path.join(fixtures, "ruled.pdf"));
  await page.getByRole("link", { name: "Smart PDF home" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Keep editing" }).click();
  await expect(
    page.getByRole("button", { name: "Upload and convert", exact: true }),
  ).toBeEnabled();
  await page.getByRole("link", { name: "Smart PDF home" }).click();
  await page.getByRole("button", { name: "Discard task and leave" }).click();
  await expect(page).toHaveURL("/");
});

test("double activation submits one conversion", async ({ page }) => {
  let count = 0;
  page.on("request", (r) => {
    if (r.method() === "POST" && r.url().includes("/api/pdf-to-excel/jobs"))
      count++;
  });
  await page
    .locator("input[type=file]")
    .setInputFiles(path.join(fixtures, "ruled.pdf"));
  const button = page.getByRole("button", {
    name: "Upload and convert",
    exact: true,
  });
  await expect(button).toBeEnabled();
  await button.evaluate((node) => {
    (node as HTMLButtonElement).click();
    (node as HTMLButtonElement).click();
  });
  await expect(
    page.getByRole("link", { name: "Download Excel", exact: true }),
  ).toBeVisible();
  expect(count).toBe(1);
});
