import { expect, test, type Page } from "@playwright/test";

async function trackNativeCloses(page: Page) {
  await page.addInitScript(() => {
    const closes: boolean[] = [];
    Reflect.set(window, "nativeDialogConnectedOnClose", closes);
    const close = HTMLDialogElement.prototype.close;
    HTMLDialogElement.prototype.close = function (value?: string) {
      closes.push(this.isConnected);
      return close.call(this, value);
    };
  });
}

for (const kind of ["preview", "confirmation", "signature"] as const)
  test(`native ${kind} dialog closes before removal`, async ({ page }) => {
    await trackNativeCloses(page);
    if (kind === "preview") {
      await page.goto("/images-to-pdf/");
      await page
        .locator("#photo-files")
        .setInputFiles("docs/ux/public-synthetic-only/image-a.png");
      await page
        .getByRole("button", { name: "Preview image 1", exact: true })
        .click();
      await page
        .getByRole("dialog", { name: "Image page preview", exact: true })
        .getByRole("button", { name: "Close preview", exact: true })
        .click();
    } else if (kind === "confirmation") {
      await page.goto("/split-pdf/");
      await page
        .locator("#pdf-file")
        .setInputFiles("tests/fixtures/split/credentials.pdf");
      await expect(
        page.getByRole("dialog", {
          name: "Create a copy without Content Credentials",
          exact: true,
        }),
      ).toBeVisible();
      await page.keyboard.press("Escape");
    } else {
      await page.goto("/sign-pdf/");
      await page
        .locator("#pdf-file")
        .setInputFiles("tests/fixtures/m5/normal-a4.pdf");
      await page
        .getByRole("button", { name: "Add signature", exact: true })
        .click();
      await page
        .getByRole("dialog", { name: "Create signature", exact: true })
        .getByRole("button", { name: "Cancel", exact: true })
        .click();
    }
    await expect(page.getByRole("dialog")).toHaveCount(0);
    const closes = await page.evaluate(
      () => Reflect.get(window, "nativeDialogConnectedOnClose") as boolean[],
    );
    expect(closes.length).toBeGreaterThan(0);
    expect(closes.every(Boolean)).toBe(true);
  });

test("leave confirmation restores focus before removal at desktop and mobile widths", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const closes: boolean[] = [];
    Reflect.set(window, "leaveDialogConnectedOnClose", closes);
    const close = HTMLDialogElement.prototype.close;
    HTMLDialogElement.prototype.close = function (value?: string) {
      if (this.classList.contains("leave-task-dialog"))
        closes.push(this.isConnected);
      return close.call(this, value);
    };
  });
  await page.goto("/images-to-pdf/");
  await page
    .locator("#photo-files")
    .setInputFiles("docs/ux/public-synthetic-only/image-a.png");
  await expect(
    page.getByRole("button", { name: "Preview image 1", exact: true }),
  ).toBeEnabled();
  const trigger = page.getByRole("button", {
    name: "← All tools",
    exact: true,
  });
  const dialog = page.getByRole("dialog", {
    name: "Leave this task?",
    exact: true,
  });
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 844 });
    for (const method of ["button", "escape"]) {
      await trigger.click();
      await expect(
        dialog.getByRole("button", { name: "Keep editing", exact: true }),
      ).toBeFocused();
      if (method === "button")
        await dialog
          .getByRole("button", { name: "Keep editing", exact: true })
          .click();
      else await page.keyboard.press("Escape");
      await expect(dialog).toHaveCount(0);
      await expect(trigger).toBeFocused();
      await expect(page.locator(".photo-list>li")).toHaveCount(1);
      const closes = await page.evaluate(
        () => Reflect.get(window, "leaveDialogConnectedOnClose") as boolean[],
      );
      expect(closes.length).toBeGreaterThan(0);
      expect(closes.every(Boolean)).toBe(true);
    }
  }
});
