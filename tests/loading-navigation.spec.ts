import { expect, test, type Page } from "@playwright/test";
import { selectToolPath } from "./navigation";

const tools = [
  ["merge-pdf", "combine-files"],
  ["split-pdf", "pdf-file"],
  ["organize-pdf", "pdf-file"],
  ["images-to-pdf", "photo-files"],
  ["sign-pdf", "pdf-file"],
  ["compress-pdf", "pdf-file"],
  ["rotate-pdf", "pdf-file"],
  ["pdf-to-jpg", "pdf-file"],
  ["watermark-pdf", "pdf-file"],
] as const;

async function checkPicker(page: Page, id: string) {
  const input = page.locator(`#${id}`);
  await expect(input).toBeVisible();
  await expect(input).toBeEnabled();
  await expect(page.locator(".panel > .status")).toBeHidden();
  await expect(page.locator(".tool-loading")).toHaveCount(0);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const picker = page.waitForEvent("filechooser", { timeout: 5_000 });
  await page.locator(`label[for="${id}"]`).tap();
  await (await picker).setFiles([]);
  await expect(input).toHaveValue("");
}

async function navigate(page: Page, path: string) {
  await selectToolPath(page, path);
}

for (const width of [390, 1280]) {
  test(`${width}: every tool-to-tool transition keeps the real picker responsive`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 844 });
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto("/");
    for (const [source] of tools) {
      await navigate(page, source);
      for (const [target, id] of tools) {
        await navigate(page, target);
        await expect(page).toHaveURL(new RegExp(`/${target}/$`));
        await checkPicker(page, id);
        await navigate(page, source);
      }
      await page
        .getByRole("button", { name: "← All tools", exact: true })
        .tap();
      await expect(page.locator(".tool-home")).toBeVisible();
      await expect(page.locator(".tool-home [role=status]")).toHaveCount(0);
    }
    expect(errors).toEqual([]);
  });
}

test("rapid navigation while cold resources are delayed leaves only the latest tool active", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  let release!: () => void;
  const barrier = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/pdf-resources.json", async (route) => {
    await barrier;
    await route.continue().catch(() => {});
  });
  await page.goto("/");
  for (const [path, id] of tools) {
    await selectToolPath(page, path);
    await checkPicker(page, id);
  }
  release();
  await expect(page.locator(".status.ready")).toBeAttached();
  await expect(page.locator(".tool-nav a.active")).toHaveAttribute(
    "href",
    "/watermark-pdf/",
  );
  await navigate(page, "compress-pdf");
  await page
    .locator("#pdf-file")
    .setInputFiles("tests/fixtures/m5/normal-a4.pdf");
  await expect(page.locator(".compress-task")).toBeVisible();
  await expect(
    page.locator(".sign-task, .split-task, .organize-task"),
  ).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("browser back and forward restore clean tool pickers without stale overlays", async ({
  page,
}) => {
  await page.goto("/");
  await page.locator("html").evaluate((element) => {
    element.setAttribute("data-audit-document", "history-navigation");
  });
  for (const [path] of tools) await selectToolPath(page, path);
  for (const [path, id] of tools.slice(0, -1).reverse()) {
    await page.goBack();
    await expect(page).toHaveURL(new RegExp(`/${path}/$`));
    await expect(page.locator("html")).toHaveAttribute(
      "data-audit-document",
      "history-navigation",
    );
    await checkPicker(page, id);
  }
  for (const [path, id] of tools.slice(1)) {
    await page.goForward();
    await expect(page).toHaveURL(new RegExp(`/${path}/$`));
    await expect(page.locator("html")).toHaveAttribute(
      "data-audit-document",
      "history-navigation",
    );
    await checkPicker(page, id);
  }
});

test("back from a completed task returns home and forward opens a fresh picker without reloading", async ({
  page,
}) => {
  await page.goto("/");
  await page.locator("html").evaluate((element) => {
    element.setAttribute("data-audit-document", "completed-navigation");
  });
  await navigate(page, "images-to-pdf");
  await page
    .locator("#photo-files")
    .setInputFiles("docs/ux/public-synthetic-only/image-a.png");
  await page
    .getByRole("button", { name: "Convert to PDF →", exact: true })
    .click();
  await expect(page.locator(".delivery")).toBeVisible();
  await page.goBack();
  await expect(page.locator(".tool-home")).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute(
    "data-audit-document",
    "completed-navigation",
  );
  await page.goForward();
  await expect(page).toHaveURL(/\/images-to-pdf\/$/);
  await checkPicker(page, "photo-files");
  await expect(page.locator(".delivery, .photo-list>li")).toHaveCount(0);
  await expect(page.locator("html")).toHaveAttribute(
    "data-audit-document",
    "completed-navigation",
  );
});
