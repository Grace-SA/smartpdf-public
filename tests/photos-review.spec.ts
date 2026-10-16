import { test, expect, type Page } from "@playwright/test";

test("large PNG estimate blocks Apply early and removing it restores generation", async ({
  page,
}) => {
  await open(page);
  await add(page);
  const png = await page.evaluate(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 4000;
    canvas.height = 3200;
    const ctx = canvas.getContext("2d")!;
    ctx.fillStyle = "blue";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    const data = canvas.toDataURL("image/png").split(",")[1]!;
    canvas.width = canvas.height = 0;
    return data;
  });
  await page.locator("#photo-files").setInputFiles({
    name: "large-synthetic.png",
    mimeType: "image/png",
    buffer: Buffer.from(png, "base64"),
  });
  await expect(page.locator(".photo-list li")).toHaveCount(2);
  await expect(
    page.getByRole("alert").filter({ hasText: "60 MiB session budget" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Apply photos", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Remove image 2", exact: true })
    .click();
  await expect(
    page.getByRole("alert").filter({ hasText: "60 MiB session budget" }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Apply photos", exact: true }).click();
  await expect(page.getByText("Page 1 of 1", { exact: true })).toBeVisible();
});

async function open(page: Page) {
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await page
    .getByRole("button", { name: "Turn Photos into PDF", exact: true })
    .click();
}
async function add(page: Page, name = "red.jpg") {
  await page
    .locator("#photo-files")
    .setInputFiles(`tests/fixtures/photos/${name}`);
  await expect(
    page.getByRole("button", { name: "Cancel photo task" }),
  ).toHaveCount(0);
  await expect(page.locator(".photo-list li")).not.toHaveCount(0);
}
async function generate(page: Page) {
  await add(page);
  await page.getByRole("button", { name: "Apply photos", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Save PDF", exact: true }),
  ).toBeVisible();
}
async function protectedExit(page: Page) {
  return page.evaluate(() => {
    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);
    return event.defaultPrevented;
  });
}
test("exit protection covers undo, redo and generated history behind imported PDF", async ({
  page,
}) => {
  await open(page);
  expect(await protectedExit(page)).toBe(false);
  await generate(page);
  expect(await protectedExit(page)).toBe(true);
  await page
    .getByRole("button", { name: "Undo Create Photos PDF", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Redo Create Photos PDF", exact: true }),
  ).toBeEnabled();
  expect(await protectedExit(page)).toBe(true);
  await page
    .getByRole("button", { name: "Redo Create Photos PDF", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Save PDF", exact: true }),
  ).toBeVisible();
  await page.locator("#pdf-file").setInputFiles("tests/fixtures/plain.pdf");
  await page
    .getByRole("button", { name: "Replace document", exact: true })
    .click();
  await expect(page.getByText("Page 1 of 2", { exact: true })).toBeVisible();
  expect(await protectedExit(page)).toBe(true);
  await page
    .getByRole("button", { name: "Clear session", exact: true })
    .click();
  await page.getByRole("button", { name: "End session", exact: true }).click();
  await expect(page.locator(".canvas-host canvas")).toHaveCount(0);
  expect(await protectedExit(page)).toBe(false);
});

test("end and replacement confirmations are modal, trap focus and cancel safely", async ({
  page,
}) => {
  await open(page);
  await generate(page);
  const clear = page.getByRole("button", {
    name: "Clear session",
    exact: true,
  });
  // Test keyboard focus restoration from an actually focused trigger.
  // WebKit deliberately does not focus buttons on pointer clicks.
  await clear.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "End session", exact: true });
  await expect(dialog).toBeVisible();
  expect(await dialog.evaluate((d) => d.matches(":modal"))).toBe(true);
  await expect(dialog.getByRole("button", { name: "Stay here" })).toBeFocused();
  // A real click outside the dialog must not start a background task.
  const box = await page.locator("#photo-files").boundingBox();
  await page.mouse.click(box!.x + 5, box!.y + 5);
  await expect(page.locator(".photo-list li")).toHaveCount(0);
  await dialog.getByRole("button", { name: "Stay here" }).focus();
  for (let i = 0; i < 6; i++) {
    await page.keyboard.press("Tab");
    expect(
      await dialog.evaluate(
        (d) =>
          d.contains(document.activeElement) ||
          document.activeElement === document.body,
      ),
    ).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(clear).toBeFocused();
  await add(page, "blue.jpg");
  await clear.click();
  await expect(
    page.getByRole("dialog", { name: "Unapplied photo changes" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Discard changes", exact: true })
    .click();
  await page.getByRole("button", { name: "Stay here", exact: true }).click();
  await page.locator("#pdf-file").setInputFiles("tests/fixtures/plain.pdf");
  const replace = page.getByRole("dialog", {
    name: "Replace current document",
  });
  await expect(replace).toBeVisible();
  expect(await replace.evaluate((d) => d.matches(":modal"))).toBe(true);
  await page.keyboard.press("Escape");
  await expect(replace).toHaveCount(0);
  await expect(page.getByText("Page 1 of 1", { exact: true })).toBeVisible();
});

for (const kind of ["timeout", "cancel"] as const) {
  test(`image checking ${kind} preserves earlier draft and permits retry`, async ({
    page,
  }) => {
    await open(page);
    await add(page);
    await page.evaluate((kind) => {
      const read = FileReader.prototype.readAsArrayBuffer;
      Reflect.set(window, "__holdPhotoRead", true);
      FileReader.prototype.readAsArrayBuffer = function (blob) {
        if (Reflect.get(window, "__holdPhotoRead")) return;
        read.call(this, blob);
      };
      const timer = window.setTimeout;
      window.setTimeout = ((
        handler: TimerHandler,
        delay?: number,
        ...args: unknown[]
      ) =>
        timer(
          handler,
          delay === 120000 && kind === "timeout" ? 50 : delay,
          ...args,
        )) as typeof window.setTimeout;
    }, kind);
    await page
      .locator("#photo-files")
      .setInputFiles("tests/fixtures/photos/blue.jpg");
    if (kind === "cancel")
      await page.getByRole("button", { name: "Cancel photo task" }).click();
    await expect(
      page.getByRole("alert").filter({
        hasText:
          kind === "timeout"
            ? "Checking images took too long"
            : "This batch was not added",
      }),
    ).toBeVisible();
    await expect(page.locator(".photo-list li")).toHaveCount(1);
    await expect(page.locator(".photo-list li")).toContainText("red.jpg");
    await page.evaluate(() => Reflect.set(window, "__holdPhotoRead", false));
    await add(page, "blue.jpg");
    await expect(page.locator(".photo-list li")).toHaveCount(2);
  });
}

test("empty preferences do not create a draft; capacity updates before Apply", async ({
  page,
}) => {
  await open(page);
  await page.getByLabel("PDF name", { exact: true }).fill("My photos");
  await page
    .getByRole("combobox", { name: "Paper", exact: true })
    .selectOption("Letter");
  expect(await protectedExit(page)).toBe(false);
  await page
    .getByRole("button", { name: "Back to PDF preview", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page
    .getByRole("button", { name: "Turn Photos into PDF", exact: true })
    .click();
  await add(page, "alpha.png");
  await expect(page.getByLabel("Session capacity")).toContainText(
    "Estimated with new PDF:",
  );
  await expect(page.getByLabel("Session capacity")).toContainText(
    "PNG estimates are conservative",
  );
  expect(await protectedExit(page)).toBe(true);
  await page
    .getByRole("button", { name: "Remove image 1", exact: true })
    .click();
  await expect.poll(() => protectedExit(page)).toBe(false);
  await expect(page.getByLabel("Session capacity")).not.toContainText(
    "Estimated with new PDF:",
  );
  await page
    .getByRole("button", { name: "Back to PDF preview", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});
