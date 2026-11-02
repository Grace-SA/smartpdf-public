import { expect, type Page } from "@playwright/test";

export async function openTools(page: Page) {
  const toggle = page.locator(".tools-toggle");
  // A cold WebKit page can finish navigation before React mounts its header.
  // Wait for the actual control before deciding whether the menu is needed.
  await toggle.waitFor({ state: "attached" });
  if (
    (await toggle.isVisible()) &&
    (await toggle.getAttribute("aria-expanded")) === "false"
  )
    await toggle.click();
}

export async function selectTool(page: Page, label: string) {
  await openTools(page);
  await page
    .locator(".tool-nav")
    .getByRole("button", { name: label, exact: true })
    .click();
}

export async function selectToolPath(page: Page, path: string) {
  await openTools(page);
  await page.locator(`.tool-nav a[href="/${path}/"]`).click();
  // Wait for React to commit the selection before the next menu interaction.
  // A completed click alone can still expose the previous expanded state.
  await expect(page).toHaveURL((url) => url.pathname === `/${path}/`);
  await expect(page.locator(".tool-nav")).toBeHidden();
}
