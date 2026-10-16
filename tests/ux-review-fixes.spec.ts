import { test, expect, type Page } from "@playwright/test";

async function split(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Split a PDF", exact: true }).click();
  await page
    .locator("#pdf-file")
    .setInputFiles("docs/ux/public-synthetic-only/demo-a.pdf");
  await page
    .getByRole("combobox", { name: "Split mode", exact: true })
    .selectOption("fixed");
  await page.getByLabel("Pages per file", { exact: true }).fill("2");
  await page.getByRole("button", { name: "Split PDF →", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "3 PDFs ready to download",
      exact: true,
    }),
  ).toBeVisible();
}

test("continuation dialog stays centered in desktop, portrait and landscape", async ({
  page,
}, info) => {
  await split(page);
  for (const [width, height] of [
    [1280, 800],
    [390, 844],
    [844, 390],
  ] as const) {
    await page.setViewportSize({ width, height });
    await page
      .getByRole("button", {
        name: "Continue editing demo-a-part-02.pdf",
        exact: true,
      })
      .click();
    const dialog = page.getByRole("dialog", {
      name: "Continue editing",
      exact: true,
    });
    await expect(dialog.locator("[data-stay]")).toBeFocused();
    const box = (await dialog.boundingBox())!;
    expect(Math.abs(box.x + box.width / 2 - width / 2)).toBeLessThan(2);
    expect(Math.abs(box.y + box.height / 2 - height / 2)).toBeLessThan(2);
    expect(box.height).toBeLessThanOrEqual(height - 32);
    await dialog.locator("[data-stay]").scrollIntoViewIfNeeded();
    await expect(dialog.locator("[data-stay]")).toBeInViewport();
    await page.screenshot({
      path: `docs/evidence/ux9-confirm-${info.project.name}-${width}.png`,
    });
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(
      page.getByRole("heading", {
        name: "3 PDFs ready to download",
        exact: true,
      }),
    ).toBeVisible();
  }
});

for (const failure of ["error", "timeout"] as const) {
  test(`failed next-page ${failure} never shows the previous page and can recover`, async ({
    page,
  }) => {
    await split(page);
    await page
      .getByRole("button", {
        name: "Preview result demo-a-part-02.pdf",
        exact: true,
      })
      .click();
    const dialog = page.getByRole("dialog", { name: "Enlarged selected page" });
    await expect(dialog.locator("canvas")).toHaveAttribute(
      "aria-label",
      /Original page 1,/,
    );
    await page.evaluate((kind) => {
      const original = HTMLCanvasElement.prototype.getContext;
      const timeout = window.setTimeout;
      (window as unknown as { restoreReview: () => void }).restoreReview =
        () => {
          HTMLCanvasElement.prototype.getContext = original;
          window.setTimeout = timeout;
        };
      if (kind === "error") {
        HTMLCanvasElement.prototype.getContext = () => {
          throw Error("synthetic render failure");
        };
      } else {
        // Trigger the actual watchdog before async page rendering completes.
        window.setTimeout = ((
          handler: TimerHandler,
          ms?: number,
          ...args: unknown[]
        ) => {
          if (ms === 120000) {
            queueMicrotask(() => {
              if (typeof handler === "function") handler(...args);
            });
            return timeout(() => {}, 0);
          }
          return timeout(handler, ms, ...args);
        }) as typeof window.setTimeout;
      }
    }, failure);
    await dialog
      .getByRole("button", { name: "Next page", exact: true })
      .click();
    await expect(dialog).toContainText(
      failure === "error" ? "could not be enlarged" : "took too long",
    );
    await expect(dialog).toContainText("2 / 2");
    await expect(dialog.locator("canvas")).toHaveCount(0);
    await page.evaluate(() =>
      (window as unknown as { restoreReview: () => void }).restoreReview(),
    );
    await dialog
      .getByRole("button", { name: "Previous page", exact: true })
      .click();
    await expect(dialog.locator("canvas")).toHaveAttribute(
      "aria-label",
      /Original page 1,/,
    );
    await dialog
      .getByRole("button", { name: "Next page", exact: true })
      .click();
    await expect(dialog.locator("canvas")).toHaveAttribute(
      "aria-label",
      /Original page 2,/,
    );
  });
}
