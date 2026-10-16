import { test, expect } from "@playwright/test";
import { openTools } from "./navigation";
import { publicTools, toolPaths, toolCatalog } from "../src/routes";

for (const width of [320, 390, 844, 1099, 1100, 1440, 1920]) {
  test(`${width}: grouped menu is bounded, stationary and fully reachable`, async ({
    page,
  }, info) => {
    await page.setViewportSize({ width, height: width === 844 ? 390 : 844 });
    await page.goto("/pdf-to-jpg/");
    const header = page.locator("header");
    await expect(page.locator(".tools-toggle")).toBeVisible();
    await expect(page.locator(".tool-nav")).toBeHidden();
    const heading = page.getByRole("heading", {
      name: "PDF to JPG / PNG",
      exact: true,
      level: 1,
    });
    const before = await heading.boundingBox();
    const headerBefore = await header.boundingBox();
    await openTools(page);
    await expect(page.locator(".tool-nav a:visible")).toHaveCount(
      publicTools.length,
    );
    await expect(page.locator(".tool-menu-group")).toHaveCount(4);
    await expect(page.locator(".tool-nav a.active")).toHaveAttribute(
      "href",
      toolPaths.raster,
    );
    expect((await heading.boundingBox())!.y).toBe(before!.y);
    expect((await header.boundingBox())!.height).toBe(headerBefore!.height);
    await expect(page.locator(".tool-shortcuts")).toBeVisible({
      visible: width >= 1100,
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    const menu = (await page.locator(".tool-nav").boundingBox())!;
    expect(menu.x).toBeGreaterThanOrEqual(0);
    expect(menu.x + menu.width).toBeLessThanOrEqual(width);
    expect(menu.y + menu.height).toBeLessThanOrEqual(width === 844 ? 390 : 844);
    await page.screenshot({ path: info.outputPath(`grouped-${width}.png`) });
    await page.locator('.tool-nav a[href="/watermark-pdf/"]').click();
    await expect(page).toHaveURL(/\/watermark-pdf\/$/);
    await expect(page.locator(".tools-toggle")).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    await expect(page.locator(".tool-nav")).toBeHidden();
    const chooser = page.waitForEvent("filechooser");
    await page.locator("#pdf-file").click();
    await (await chooser).setFiles([]);
  });
}

test("every upload page shows every other tool; all discovery surfaces share the catalogue", async ({
  page,
}) => {
  await page.goto("/");
  const expected = publicTools.map((id) => toolPaths[id]).sort();
  expect(
    (
      await page
        .locator(".tool-cards a")
        .evaluateAll((els) => els.map((e) => e.getAttribute("href")))
    ).sort(),
  ).toEqual(expected);
  expect(
    (
      await page
        .locator(".footer-tool-links a")
        .evaluateAll((els) => els.map((e) => e.getAttribute("href")))
    ).sort(),
  ).toEqual(expected);
  await openTools(page);
  expect(
    (
      await page
        .locator(".tool-nav a")
        .evaluateAll((els) => els.map((e) => e.getAttribute("href")))
    ).sort(),
  ).toEqual(expected);
  for (const id of publicTools) {
    await page.goto(toolPaths[id]);
    await expect(page.locator(".more-tools-grid > a")).toHaveCount(
      publicTools.length - 1,
    );
    const actual = await page
      .locator(".more-tools-grid > a")
      .evaluateAll((els) => els.map((e) => e.getAttribute("href")));
    expect(actual.sort()).toEqual(
      expected.filter((path) => path !== toolPaths[id]),
    );
    await expect(
      page.locator(`.more-tools a[href="${toolPaths[id]}"]`),
    ).toHaveCount(0);
    for (const other of publicTools.filter((other) => other !== id))
      await expect(
        page.locator(`.more-tools a[href="${toolPaths[other]}"] h3`),
      ).toHaveText(toolCatalog[other].title);
  }
});

test("desktop shortcuts work and the grouped menu supports outside dismissal and keyboard", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await expect(page.locator(".tool-shortcuts a")).toHaveCount(3);
  for (const path of ["merge-pdf", "split-pdf", "compress-pdf"]) {
    await page.locator(`.tool-shortcuts a[href="/${path}/"]`).click();
    await expect(page).toHaveURL(new RegExp(`/${path}/$`));
    await expect(
      page.locator(`.tool-shortcuts a[href="/${path}/"]`),
    ).toHaveAttribute("aria-current", "page");
  }
  await openTools(page);
  await page.keyboard.press("Escape");
  await expect(page.locator(".tools-toggle")).toBeFocused();
  await expect(page.locator(".tool-nav")).toBeHidden();
  await page.keyboard.press("Enter");
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("button", { name: "Close tools", exact: true }),
  ).toBeFocused();
  // Dismiss using a visible outside target, then check the actual native picker.
  await page.locator("header .version").click();
  const chooser = page.waitForEvent("filechooser");
  await page.locator("#pdf-file").click();
  await (await chooser).setFiles([]);
  await expect(page.locator(".tool-nav")).toBeHidden();
});
