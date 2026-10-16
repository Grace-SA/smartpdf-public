import { test, expect, type Page } from "@playwright/test";
import { selectToolPath } from "./navigation";

async function tapPicker(
  page: Page,
  id: string,
  touch: boolean,
  files: string[],
) {
  const label = page.locator(`label.native-file-picker:has(#${id})`);
  await expect(label).toBeVisible();
  await expect(page.locator(`#${id}`)).toBeEnabled();
  const box = (await label.boundingBox())!;
  const point = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  expect(
    await page.evaluate(
      ({ x, y, id }) => document.elementFromPoint(x, y)?.id === id,
      { ...point, id },
    ),
    "Visible picker centre must hit the native file input",
  ).toBe(true);
  const chooser = page.waitForEvent("filechooser", { timeout: 8000 });
  // Use the native input's real pointer action, with Playwright's layout and
  // actionability checks, rather than clicking a coordinate sampled earlier.
  if (touch) await page.locator(`#${id}`).tap();
  else await page.locator(`#${id}`).click();
  await (await chooser).setFiles(files);
}

for (const width of [390, 1440])
  for (const route of [
    "restart",
    "tools-raster",
    "tools-split",
    "tools-merge",
  ]) {
    test(`${width}: download → ${route} → real file picker`, async ({
      page,
    }) => {
      const touch = width === 390;
      await page.setViewportSize({ width, height: 900 });
      for (const single of [false, true]) {
        await page.goto("/pdf-to-jpg/");
        await tapPicker(page, "pdf-file", touch, [
          "tests/fixtures/m8-device.pdf",
        ]);
        if (single) {
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
        const download = page.waitForEvent("download");
        await page
          .getByRole("button", {
            name: single ? "Download JPG" : "Download ZIP",
            exact: true,
          })
          .click();
        await download;
        if (route === "restart")
          await page.getByRole("button", { name: /Choose new files/ }).click();
        else
          await selectToolPath(
            page,
            route === "tools-split"
              ? "split-pdf"
              : route === "tools-merge"
                ? "merge-pdf"
                : "pdf-to-jpg",
          );
        await expect(page.locator(".delivery,dialog[open]")).toHaveCount(0);
        await expect(page.locator(".task-notice-backdrop,[inert]")).toHaveCount(
          0,
        );
        const merge = route === "tools-merge",
          id = merge ? "combine-files" : "pdf-file";
        // Cancel native selection, then reopen it: no stale disabled state.
        await tapPicker(page, id, touch, []);
        await tapPicker(
          page,
          id,
          touch,
          merge
            ? [
                "docs/ux/public-synthetic-only/demo-a.pdf",
                "docs/ux/public-synthetic-only/demo-b.pdf",
              ]
            : ["tests/fixtures/m8-device.pdf"],
        );
        await expect(
          page.locator(
            merge
              ? ".combine-task:not(.empty-inputs)"
              : route === "tools-split"
                ? ".split-task"
                : ".raster-task",
          ),
        ).toBeVisible();
      }
    });
  }
