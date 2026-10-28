import { expect, type Page } from "@playwright/test";

export async function openTools(page: Page) {
  const toggle = page.locator(".tools-toggle");
  // A cold WebKit page can finish navigation before React mounts its header.
  // Wait for the actual control before deciding whether the menu is needed.
  await expect(toggle).toBeVisible();
  if ((await toggle.getAttribute("aria-expanded")) === "false")
    await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(page.locator(".tool-nav")).toBeVisible();
}

async function menuSelectionCommitted(page: Page) {
  // WebKit can acknowledge a native click before React commits the close.
  // A subsequent open must not read the previous selection's expanded state.
  // Do not wait for a destination URL: unsaved tasks may first ask to leave.
  await expect(page.locator(".tool-nav")).toBeHidden();
  await expect(page.locator(".tools-toggle")).toHaveAttribute(
    "aria-expanded",
    "false",
  );
}

export async function selectTool(page: Page, label: string) {
  await openTools(page);
  await page
    .locator(".tool-nav")
    .getByRole("button", { name: label, exact: true })
    .click();
  await menuSelectionCommitted(page);
}

export async function selectToolPath(page: Page, path: string) {
  await openTools(page);
  await page.locator(`.tool-nav a[href="/${path}/"]`).click();
  await menuSelectionCommitted(page);
}
