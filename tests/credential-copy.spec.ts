import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";
test("standard-bearing PDFs require explicit conversion and preserve a usable preview and split", async ({
  page,
}) => {
  test.setTimeout(180000);
  page.on("dialog", (d) => d.accept());
  const manifest = JSON.parse(
    await readFile("docs/private-samples/m4-full/manifest.json", "utf8"),
  );
  for (const id of ["W051", "W061", "W107", "W217"]) {
    await page.goto("/");
    await expect(page.getByText("Ready for local processing")).toBeVisible();
    await page.route(/^https?:/, (route) => route.abort());
    const source = manifest.rows.find((r: { id: string }) => r.id === id);
    await page.locator("#pdf-file").setInputFiles({
      name: `${id}.pdf`,
      mimeType: "application/pdf",
      buffer: await readFile(source.path),
    });
    await expect(page.locator(".canvas-host canvas")).toBeVisible();
    await page
      .getByRole("button", { name: "Create ordinary PDF copy", exact: true })
      .click();
    const dialog = page.getByRole("dialog", {
      name: "Create an ordinary PDF copy",
    });
    await dialog.getByRole("button", { name: "Stay here" }).click();
    await expect(
      page.getByText(/This new ordinary PDF does not claim/),
    ).toHaveCount(0);
    await page
      .getByRole("button", { name: "Create ordinary PDF copy", exact: true })
      .click();
    await dialog
      .getByRole("button", {
        name: "Create ordinary copy without standard claims",
        exact: true,
      })
      .click();
    await expect(
      page.getByText(/This new ordinary PDF does not claim/),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Split a PDF", exact: true })
      .click();
    const n = source.currentPages;
    const middle = Math.floor(n / 2);
    await page
      .getByLabel("Page groups, one per line")
      .fill(n === 1 ? "1" : `1-${middle}\n${middle + 1}-${n}`);
    await page.getByLabel(/^Allow adjustment/).check();
    await page
      .getByRole("button", { name: "Create split results", exact: true })
      .click();
    await expect(
      page.getByRole("region", { name: "Session results" }).locator("li"),
    ).toHaveCount(n === 1 ? 2 : 3, { timeout: 130000 });
    await page.unroute(/^https?:/);
  }
});
test("C2PA local originals require consent and produce editable copies offline", async ({
  page,
}) => {
  test.setTimeout(120000);
  const manifest = JSON.parse(
    await readFile("docs/private-samples/m4-full/manifest.json", "utf8"),
  );
  for (const id of ["W229", "W242"]) {
    await page.goto("/");
    await expect(page.getByText("Ready for local processing")).toBeVisible();
    await page.route(/^https?:/, (route) => route.abort());
    const source = manifest.rows.find((r: { id: string }) => r.id === id);
    const file = {
      name: `${id}.pdf`,
      mimeType: "application/pdf",
      buffer: await readFile(source.path),
    };
    await page.locator("#pdf-file").setInputFiles(file);
    const dialog = page.getByRole("dialog", {
      name: "Create a copy without Content Credentials",
    });
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "Stay here" }).click();
    await expect(page.getByText("Page 1 of 3", { exact: true })).toHaveCount(0);
    await page.locator("#pdf-file").setInputFiles(file);
    await dialog
      .getByRole("button", {
        name: "Create copy without credentials",
        exact: true,
      })
      .click();
    await expect(page.getByText("Page 1 of 3", { exact: true })).toBeVisible();
    await expect(page.getByText(/This new PDF does not retain/)).toBeVisible();
    await page
      .getByRole("button", { name: "Split a PDF", exact: true })
      .click();
    await page.getByLabel("Page groups, one per line").fill("1\n2-3");
    const adjust = page.getByRole("checkbox");
    for (const c of await adjust.all())
      if (await c.isVisible()) await c.check();
    await page
      .getByRole("button", { name: "Create split results", exact: true })
      .click();
    await expect(
      page.getByRole("region", { name: "Session results" }).locator("li"),
    ).toHaveCount(3);
    await page.unroute(/^https?:/);
  }
});
