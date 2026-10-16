import { expect, test } from "@playwright/test";

test("homepage does not load PDF engines or signature fonts", async ({
  page,
}) => {
  const heavyRequests: string[] = [];
  page.on("request", (request) => {
    if (/pdf-resources\.json|qpdf\.wasm|\/sign-fonts\//.test(request.url()))
      heavyRequests.push(request.url());
  });
  await page.goto("/");
  await expect(
    page.getByRole("heading", {
      name: "Free and private PDF tools. No uploads.",
    }),
  ).toBeVisible();
  await page.waitForTimeout(1_200);
  expect(heavyRequests).toEqual([]);
  await expect(page.locator(".tool-home [role=status]")).toHaveCount(0);
});

for (const [path, picker] of [
  ["merge-pdf", "#combine-files"],
  ["split-pdf", "#pdf-file"],
  ["organize-pdf", "#pdf-file"],
  ["images-to-pdf", "#photo-files"],
  ["sign-pdf", "#pdf-file"],
  ["compress-pdf", "#pdf-file"],
  ["rotate-pdf", "#pdf-file"],
] as const) {
  test(`${path} prepares silently without moving the file picker`, async ({
    page,
  }) => {
    let release!: () => void;
    const barrier = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route("**/pdf-resources.json", async (route) => {
      await barrier;
      await route.continue();
    });
    await page.goto(`/${path}/`);
    const input = page.locator(picker);
    await expect(input).toBeEnabled();
    await expect(page.locator(".status.loading")).toBeAttached();
    await expect(page.locator(".panel > .status")).toBeHidden();
    const label = page.locator(`label[for="${picker.slice(1)}"]`);
    await expect(label).toBeVisible();
    const before = await label.boundingBox();
    release();
    await expect(page.locator(".status.ready")).toBeAttached();
    await expect(page.locator(".panel > .status")).toBeHidden();
    const after = await label.boundingBox();
    expect(before).not.toBeNull();
    expect(after).not.toBeNull();
    expect(Math.abs(after!.y - before!.y)).toBeLessThanOrEqual(1);
  });
}

test("slow engine loading accepts a PDF and opens it automatically", async ({
  page,
}) => {
  let release!: () => void;
  const barrier = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/pdf-resources.json", async (route) => {
    await barrier;
    await route.continue();
  });
  await page.goto("/split-pdf/");
  await expect(page.locator("#pdf-file")).toBeEnabled();
  await page
    .locator("#pdf-file")
    .setInputFiles("tests/fixtures/m5/normal-a4.pdf");
  await expect(
    page.getByText("Opening your PDF… Your file stays on this device."),
  ).toBeVisible();
  await page
    .locator("#pdf-file")
    .setInputFiles("tests/fixtures/m5/landscape.pdf");
  await expect(
    page.getByRole("dialog", { name: "Leave this task?" }),
  ).toHaveCount(0);
  release();
  await expect(
    page.getByRole("heading", { name: "Split settings", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".split-task h2").first()).toHaveText(
    "landscape.pdf",
  );
});

test("failed initialization retries the selected PDF without reselection", async ({
  page,
}) => {
  let attempts = 0;
  await page.route("**/pdf-resources.json", async (route) => {
    if (++attempts === 1)
      await route.fulfill({ status: 503, body: "Unavailable" });
    else await route.continue();
  });
  await page.goto("/split-pdf/");
  await page
    .locator("#pdf-file")
    .setInputFiles("tests/fixtures/m5/normal-a4.pdf");
  await page
    .getByRole("button", { name: "Retry loading", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Split settings", exact: true }),
  ).toBeVisible();
  expect(attempts).toBe(2);
});

test("signature fonts load only for the chosen typed style and retry without losing the name", async ({
  page,
}) => {
  const fonts: string[] = [];
  let fail = true;
  await page.route("**/sign-fonts/*.ttf", async (route) => {
    fonts.push(new URL(route.request().url()).pathname);
    if (fail) {
      fail = false;
      await route.fulfill({ status: 503, body: "Unavailable" });
    } else await route.continue();
  });
  await page.goto("/sign-pdf/");
  await page
    .locator("#pdf-file")
    .setInputFiles("tests/fixtures/m5/normal-a4.pdf");
  await page
    .getByRole("button", { name: "Add signature", exact: true })
    .click();
  expect(fonts).toEqual([]);
  await page.getByRole("tab", { name: "Type", exact: true }).click();
  await page
    .getByRole("textbox", { name: "Your name", exact: true })
    .fill("Alex Chen");
  await page.getByRole("button", { name: "Retry style", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Use signature", exact: true }),
  ).toBeEnabled();
  await expect(
    page.getByRole("textbox", { name: "Your name", exact: true }),
  ).toHaveValue("Alex Chen");
  expect(fonts).toEqual([
    "/sign-fonts/Kalam-Regular.ttf",
    "/sign-fonts/Kalam-Regular.ttf",
  ]);
});

test("slow multi-file editors preserve selections during leave confirmation", async ({
  page,
}) => {
  for (const kind of ["photos", "combine"] as const) {
    let release!: () => void;
    const barrier = new Promise<void>((resolve) => {
      release = resolve;
    });
    const pattern =
      kind === "photos"
        ? /\/assets\/PhotoPanel-[^/]+\.js$/
        : /\/assets\/CombinePanel-[^/]+\.js$/;
    await page.route(pattern, async (route) => {
      await barrier;
      await route.continue();
    });
    await page.goto(kind === "photos" ? "/images-to-pdf/" : "/merge-pdf/");
    await page
      .locator(kind === "photos" ? "#photo-files" : "#combine-files")
      .setInputFiles(
        kind === "photos"
          ? "docs/ux/public-synthetic-only/image-a.png"
          : "docs/ux/public-synthetic-only/demo-a.pdf",
      );
    await page
      .getByRole("button", { name: "← All tools", exact: true })
      .click();
    const dialog = page.getByRole("dialog", {
      name: "Leave this task?",
      exact: true,
    });
    await expect(dialog).toBeVisible();
    release();
    await expect(page.locator(".photo-list>li")).toHaveCount(0);
    await dialog
      .getByRole("button", { name: "Keep editing", exact: true })
      .click();
    await expect(page.locator(".photo-list>li")).toHaveCount(1);
    await page
      .getByRole("button", { name: "← All tools", exact: true })
      .click();
    await dialog
      .getByRole("button", { name: "Discard task and leave", exact: true })
      .click();
    await expect(page.locator(".product-app")).toHaveAttribute(
      "data-screen",
      "home",
    );
    await page.unroute(pattern);
  }
});

test("photo editor chunk failure preserves selected files for retry", async ({
  page,
}) => {
  let attempts = 0;
  await page.route(
    /\/assets\/PhotoPanel-[^/?]+\.js(?:\?.*)?$/,
    async (route) => {
      if (++attempts === 1)
        await route.fulfill({
          status: 503,
          body: "Unavailable",
          contentType: "text/javascript",
        });
      else await route.continue();
    },
  );
  await page.goto("/images-to-pdf/");
  await page
    .locator("#photo-files")
    .setInputFiles("docs/ux/public-synthetic-only/image-a.png");
  await page
    .getByRole("button", { name: "Retry loading", exact: true })
    .click();
  await expect(page.locator(".photo-list>li")).toHaveCount(1);
  expect(attempts).toBe(2);
});
