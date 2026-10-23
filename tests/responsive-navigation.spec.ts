import { test, expect, type Page } from "@playwright/test";
import { openTools, selectToolPath } from "./navigation";
import { publicTools } from "../src/routes";
const tools = [
  ["merge-pdf", "combine-files", ".combine-task:not(.empty-inputs)"],
  ["split-pdf", "pdf-file", ".split-task"],
  ["organize-pdf", "pdf-file", ".organize-task"],
  ["images-to-pdf", "photo-files", ".photo-list>li"],
  ["sign-pdf", "pdf-file", ".sign-task"],
  ["compress-pdf", "pdf-file", ".compress-task"],
  ["rotate-pdf", "pdf-file", ".rotate-task"],
  ["pdf-to-jpg", "pdf-file", ".raster-task"],
  ["watermark-pdf", "pdf-file", ".watermark-task"],
  ["add-page-numbers", "pdf-file", ".numbers-task"],
] as const;
async function nativePick(page: Page, id: string, files: string[]) {
  const chooser = page.waitForEvent("filechooser");
  await page.locator(`#${id}`).click();
  await (await chooser).setFiles(files);
}

for (const width of [390, 1440]) {
  test(`${width}: selecting the completed tool starts a fresh task`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/images-to-pdf/");
    await nativePick(page, "photo-files", [
      "docs/ux/public-synthetic-only/image-a.png",
    ]);
    await page
      .getByRole("button", { name: "Convert to PDF →", exact: true })
      .click();
    await expect(page.locator(".delivery")).toBeVisible();
    await selectToolPath(page, "images-to-pdf");
    await expect(page.locator("#photo-files")).toBeVisible();
    await expect(
      page.locator(".delivery,.photo-list>li,dialog[open]"),
    ).toHaveCount(0);
    await nativePick(page, "photo-files", [
      "docs/ux/public-synthetic-only/image-b.png",
    ]);
    await expect(page.locator(".photo-list>li")).toHaveCount(1);
  });
  test(`${width}: all tools retain navigation before and after file selection`, async ({
    page,
  }, info) => {
    await page.setViewportSize({ width, height: 900 });
    for (const [path, id, editor] of tools) {
      await test.step(path, async () => {
        await page.goto(`/${path}/`);
        const before = (await page.locator("header").boundingBox())!.height;
        await openTools(page);
        await expect(page.locator(".tool-nav a:visible")).toHaveCount(
          publicTools.length,
        );
        await expect(
          page.locator(`.tool-nav a[href="/${path}/"]`),
        ).toHaveAttribute("aria-current", "page");

        await page
          .getByRole("button", { name: "Close tools", exact: true })
          .click();
        const fixture = "docs/ux/public-synthetic-only/";
        await nativePick(
          page,
          id,
          id === "photo-files"
            ? [fixture + "image-a.png"]
            : id === "combine-files"
              ? [fixture + "demo-a.pdf", fixture + "demo-b.pdf"]
              : ["tests/fixtures/m8-device.pdf"],
        );
        await expect(page.locator(editor).first()).toBeVisible();
        expect(
          (await page.locator("header").boundingBox())!.height,
        ).toBeCloseTo(before, 0);
        await openTools(page);
        await expect(page.locator(".tool-nav a:visible")).toHaveCount(
          publicTools.length,
        );
        // Choosing the current tool closes the menu and preserves the task.
        await page.locator(`.tool-nav a[href="/${path}/"]`).click();
        await expect(page.locator(editor).first()).toBeVisible();
        await expect(page.locator("dialog[open]")).toHaveCount(0);
        await openTools(page);
        const next = path === "split-pdf" ? "merge-pdf" : "split-pdf";
        await page.locator(`.tool-nav a[href="/${next}/"]`).click();
        await page.waitForFunction(
          (next) =>
            location.pathname === `/${next}/` ||
            !!document.querySelector("dialog[open]"),
          next,
        );
        if (
          await page
            .getByRole("button", { name: "Keep editing", exact: true })
            .isVisible()
        ) {
          await page
            .getByRole("button", { name: "Keep editing", exact: true })
            .click();
          await expect(page.locator(editor).first()).toBeVisible();
          await selectToolPath(page, next);
          await page
            .getByRole("button", {
              name: "Discard task and leave",
              exact: true,
            })
            .click();
        }
        await expect(page).toHaveURL(new RegExp(`/${next}/$`));
        await expect(
          page.locator(next === "split-pdf" ? "#pdf-file" : "#combine-files"),
        ).toBeVisible();
        await expect(page.locator(".delivery,dialog[open]")).toHaveCount(0);
      });
    }
    await openTools(page);
    await page.screenshot({ path: info.outputPath(`tools-${width}.png`) });
  });
}

test("menu keyboard, outside click, resizing and all viewport layouts", async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/split-pdf/");
  const toggle = page.locator(".tools-toggle");
  const heading = page.getByRole("heading", {
    name: "Split PDF",
    exact: true,
    level: 1,
  });
  const y = (await heading.boundingBox())!.y;
  await toggle.focus();
  await page.keyboard.press("Enter");
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  expect((await heading.boundingBox())!.y).toBe(y);
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("button", { name: "Close tools", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(toggle).toBeFocused();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await page.setViewportSize({ width: 1280, height: 900 });
  await openTools(page);
  // The grouped panel overlays the picker at this width. Dismiss it through
  // a visible outside target before exercising native file selection.
  await page.locator("header .version").click();
  await nativePick(page, "pdf-file", []);
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  for (const width of [320, 390, 800, 1024, 1280, 1400, 1401, 1440]) {
    await page.setViewportSize({ width, height: 844 });
    await openTools(page);
    await expect(page.locator(".tool-nav a:visible")).toHaveCount(
      publicTools.length,
    );
    const layout = await page.evaluate(() => {
      const nav = document.querySelector(".tool-nav")!.getBoundingClientRect();
      const brand = document
        .querySelector("header .brand")!
        .getBoundingClientRect();
      return {
        overflow: document.documentElement.scrollWidth > innerWidth,
        intersects:
          nav.left < brand.right &&
          nav.right > brand.left &&
          nav.top < brand.bottom &&
          nav.bottom > brand.top,
        right: nav.right,
        left: nav.left,
        width: innerWidth,
      };
    });
    expect(layout.overflow).toBe(false);
    expect(layout.intersects).toBe(false);
    expect(layout.left).toBeGreaterThanOrEqual(0);
    expect(layout.right).toBeLessThanOrEqual(width);
    await page.screenshot({ path: info.outputPath(`navigation-${width}.png`) });

    await page
      .getByRole("button", { name: "Close tools", exact: true })
      .click();
  }
});
