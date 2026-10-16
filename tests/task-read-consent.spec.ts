import { selectTool } from "./navigation";
import { test, expect } from "@playwright/test";

test("copy preparation blocks background edits and cancellation preserves the original task", async ({
  page,
}) => {
  await page.goto("/");
  await selectTool(page, "Split a PDF");
  await page
    .locator("#pdf-file")
    .setInputFiles("tests/fixtures/split/ordinary.pdf");
  await expect(page.getByLabel("Range 1 to", { exact: true })).toHaveValue("2");
  // Hold only the explicitly confirmed copy job, to exercise real cancellation.
  await page.evaluate(() => {
    const original = Worker.prototype.postMessage;
    Worker.prototype.postMessage = function (this: Worker, message, ...args) {
      if (message?.ordinary === true && message?.confirmed === true) return;
      return Reflect.apply(original, this, [message, ...args]);
    } as typeof original;
  });
  await page
    .getByRole("button", { name: "Create ordinary PDF copy", exact: true })
    .click();
  await page
    .getByRole("button", {
      name: "Create ordinary copy without standard claims",
      exact: true,
    })
    .click();
  const busy = page.getByRole("dialog", {
    name: "Processing PDF",
    exact: true,
  });
  await expect(busy).toBeVisible();
  await expect(
    page.getByLabel("Range 1 to", { exact: true }).click({ timeout: 500 }),
  ).rejects.toThrow();
  await busy
    .getByRole("button", { name: "Cancel processing", exact: true })
    .click();
  await expect(busy).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "ordinary.pdf", exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Range 1 to", { exact: true })).toHaveValue("2");
  await expect(page.locator(".delivery")).toHaveCount(0);
});

test("task preview uses the shared modal and never inserts a bottom preview", async ({
  page,
}) => {
  await page.goto("/");
  await selectTool(page, "Combine PDFs");
  await page
    .locator("#combine-files")
    .setInputFiles("docs/ux/public-synthetic-only/demo-a.pdf");
  await page
    .getByRole("button", { name: "Preview PDF 1", exact: true })
    .click();
  const reader = page.getByRole("dialog", { name: "Enlarged selected page" });
  await expect(reader.locator("canvas")).toHaveCount(1);
  await reader.getByLabel("Page number", { exact: true }).selectOption("5");
  await expect(reader.locator("canvas")).toHaveAttribute(
    "aria-label",
    /Original page 6,/,
  );
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await expect(
      reader.getByRole("button", { name: "Close preview", exact: true }),
    ).toBeInViewport();
    await expect(
      reader.getByLabel("Page number", { exact: true }),
    ).toBeInViewport();
  }
  await reader
    .getByRole("button", { name: "Close preview", exact: true })
    .click();
  await expect(page.locator(".preview, .session-history")).toHaveCount(0);
  await expect(page.locator(".combine-task")).toBeVisible();
});

for (const kind of ["ordinary", "credentials"] as const) {
  test(`${kind} consent prepares a source within the task, not a completed task`, async ({
    page,
  }) => {
    await page.goto("/");
    await selectTool(page, "Split a PDF");
    await page
      .locator("#pdf-file")
      .setInputFiles(`tests/fixtures/split/${kind}.pdf`);
    if (kind === "ordinary")
      await page
        .getByRole("button", { name: "Create ordinary PDF copy", exact: true })
        .click();
    const dialog = page.getByRole("dialog", {
      name:
        kind === "ordinary"
          ? "Create an ordinary PDF copy"
          : "Create a copy without Content Credentials",
      exact: true,
    });
    await expect(dialog).toBeVisible();
    await page.setViewportSize({ width: 390, height: 844 });
    const box = (await dialog.boundingBox())!;
    expect(Math.abs(box.x + box.width / 2 - 195)).toBeLessThan(2);
    await dialog
      .getByRole("button", {
        name:
          kind === "ordinary"
            ? "Create ordinary copy without standard claims"
            : "Create copy without credentials",
        exact: true,
      })
      .click();
    await expect(
      page.getByRole("heading", {
        name:
          kind === "ordinary"
            ? "ordinary-ordinary.pdf"
            : "credentials-without-credentials.pdf",
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("dialog", { name: "Processing PDF", exact: true }),
    ).toHaveCount(0);
    await expect(page.getByLabel("Range 1 to", { exact: true })).toBeVisible();
    await expect(page.locator(".product-app")).toHaveAttribute(
      "data-screen",
      "task",
    );
    await expect(page.locator(".delivery")).toHaveCount(0);
    await page.getByLabel("Range 1 to", { exact: true }).fill("1");
    await page
      .getByRole("button", { name: "Split PDF →", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Download PDF", exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Choose new files", exact: true })
      .click();
    await expect(page.locator("#pdf-file")).toHaveValue("");
    await expect(page.locator(".split-task, .delivery")).toHaveCount(0);
  });
}
