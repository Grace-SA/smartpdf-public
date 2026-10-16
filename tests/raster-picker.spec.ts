import { selectTool } from "./navigation";
import { test, expect, type Page } from "@playwright/test";

async function pick(page: Page, id: string, files: string[]) {
  const input = page.locator(`#${id}`);
  await expect(input).toBeEnabled();
  const chooser = page.waitForEvent("filechooser");
  await input.click();
  await (await chooser).setFiles(files);
}

for (const width of [390, 1280]) {
  for (const target of ["split", "combine"]) {
    test(`M8 download → ${target}: native chooser and import at ${width}px`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/pdf-to-jpg/");
      for (let round = 0; round < 2; round++) {
        await pick(page, "pdf-file", ["tests/fixtures/m8-device.pdf"]);
        if (round === 1) {
          await page
            .getByRole("radio", { name: "Page range", exact: true })
            .check();
          await page
            .getByRole("textbox", { name: "Page range", exact: true })
            .fill("2");
        }
        await page
          .getByRole("button", { name: "Convert to JPG →", exact: true })
          .click();
        const download = page.getByRole("button", {
          name: round === 0 ? "Download ZIP" : "Download JPG",
          exact: true,
        });
        await expect(download).toBeVisible();
        const downloaded = page.waitForEvent("download");
        await download.click();
        await downloaded;
        await expect(page.locator(".task-notice-backdrop,[inert]")).toHaveCount(
          0,
        );
        await expect(page.locator("dialog[open]")).toHaveCount(0);
        await selectTool(
          page,
          target === "split" ? "Split a PDF" : "Combine PDFs",
        );
        await pick(
          page,
          target === "split" ? "pdf-file" : "combine-files",
          target === "split"
            ? ["tests/fixtures/m8-device.pdf"]
            : [
                "docs/ux/public-synthetic-only/demo-a.pdf",
                "docs/ux/public-synthetic-only/demo-b.pdf",
              ],
        );
        await expect(
          page.locator(
            target === "split"
              ? ".split-task"
              : ".combine-task:not(.empty-inputs)",
          ),
        ).toBeVisible();
        await page
          .getByRole("button", { name: "← All tools", exact: true })
          .click();
        if (target === "combine")
          await page
            .getByRole("button", {
              name: "Discard task and leave",
              exact: true,
            })
            .click();
        await selectTool(page, "PDF to JPG / PNG");
      }
    });
  }
}
