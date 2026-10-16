import { expect, test } from "@playwright/test";

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
