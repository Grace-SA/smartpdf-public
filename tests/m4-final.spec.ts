import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";
for (const groups of ["1\n2-3\n4-5", "1\n2\n3\n4\n5"])
  test(`W217 empty-tag split ${groups.split("\n").length}`, async ({
    page,
  }) => {
    test.setTimeout(130000);
    await page.goto("/");
    await expect(page.getByText("Ready for local processing")).toBeVisible();
    await page.route(/^https?:/, (route) => route.abort());
    await page.locator("#pdf-file").setInputFiles({
      name: "W217-ordinary.pdf",
      mimeType: "application/pdf",
      buffer: await readFile(
        "docs/private-samples/m4-improve/W217/ordinary/copy.pdf",
      ),
    });
    await expect(page.getByText("Page 1 of 5", { exact: true })).toBeVisible();
    await page
      .getByRole("button", { name: "Split a PDF", exact: true })
      .click();
    await page.getByLabel("Page groups, one per line").fill(groups);
    await page.getByLabel(/^Allow adjustment/).check();
    await page
      .getByRole("button", { name: "Create split results", exact: true })
      .click();
    await expect(
      page.getByRole("region", { name: "Session results" }).locator("li"),
    ).toHaveCount(groups.split("\n").length + 1, { timeout: 120000 });
    const history = page.getByRole("region", { name: "Document history" });
    await expect(
      history.getByRole("button", { name: /^Undo Split PDF/ }),
    ).toBeEnabled();
  });
