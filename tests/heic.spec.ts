import { test, expect } from "@playwright/test";
import { readFile, mkdir } from "node:fs/promises";
import { PDFDocument } from "pdf-lib";
test("HEIC-20 mixed photos work offline and save exactly twenty pages", async ({
  page,
  context,
  browserName,
}) => {
  test.setTimeout(120000);
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await page
    .getByRole("button", { name: "Turn Photos into PDF", exact: true })
    .click();
  const requests: string[] = [];
  page.on("request", (request) => {
    if (/^https?:/.test(request.url())) requests.push(request.url());
  });
  const heic = await readFile("tests/fixtures/photos/synthetic.heic");
  const jpeg = await readFile("tests/fixtures/photos/red.jpg");
  const png = await readFile("tests/fixtures/photos/alpha.png");
  const icc = await readFile("tests/fixtures/photos/synthetic-icc.heic");
  const rotated = await readFile(
    "tests/fixtures/photos/synthetic-rotated.heic",
  );
  const selected = Array.from({ length: 20 }, (_, i) => ({
    name: `photo-${i}.${i === 18 ? "jpg" : i === 19 ? "png" : "heic"}`,
    mimeType: i === 18 ? "image/jpeg" : i === 19 ? "image/png" : "image/heic",
    buffer:
      i === 18
        ? jpeg
        : i === 19
          ? png
          : i === 16
            ? icc
            : i === 17
              ? rotated
              : heic,
  }));
  // Materialize synthetic local Files before disconnecting.
  await page.evaluate(
    (entries) => {
      const files = entries.map(
        (entry) =>
          new File([new Uint8Array(entry.bytes)], entry.name, {
            type: entry.mimeType,
          }),
      );
      (window as typeof window & { heicTestFiles: File[] }).heicTestFiles =
        files;
    },
    selected.map(({ buffer, ...rest }) => ({ ...rest, bytes: [...buffer] })),
  );
  // Windows Playwright WebKit offline mode also breaks FileReader for local
  // in-memory Files (NotReadableError). Deny every HTTP request there instead.
  if (browserName === "webkit")
    await context.route(/^https?:/, (route) => route.abort());
  else await context.setOffline(true);
  await page.evaluate(() => {
    const transfer = new DataTransfer();
    for (const file of (window as typeof window & { heicTestFiles: File[] })
      .heicTestFiles)
      transfer.items.add(file);
    const input = document.querySelector<HTMLInputElement>("#photo-files")!;
    input.files = transfer.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await expect(
    page.getByRole("button", { name: "Cancel photo task" }),
  ).toHaveCount(0, { timeout: 90000 });
  await page.getByRole("button", { name: "Apply photos", exact: true }).click();
  await expect(page.getByText("Page 1 of 20", { exact: true })).toBeVisible({
    timeout: 60000,
  });
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Save PDF", exact: true }).click();
  await mkdir("docs/private-samples/heic", { recursive: true });
  const output = `docs/private-samples/heic/twenty-${test.info().project.name || "chromium"}.pdf`;
  await (await downloaded).saveAs(output);
  expect((await PDFDocument.load(await readFile(output))).getPageCount()).toBe(
    20,
  );
  expect(requests).toEqual([]);
});
test("HEIC-20 twelve-megapixel batch can be cancelled and retried", async ({
  page,
}) => {
  test.setTimeout(180000);
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await page
    .getByRole("button", { name: "Turn Photos into PDF", exact: true })
    .click();
  const buffer = await readFile("tests/fixtures/photos/synthetic-12mp.heic");
  const batch = Array.from({ length: 20 }, (_, i) => ({
    name: `large-${i}.heic`,
    mimeType: "image/heic",
    buffer,
  }));
  await page.locator("#photo-files").setInputFiles(batch);
  await page.getByRole("button", { name: "Cancel photo task" }).click();
  await expect(page.getByText(/This batch was not added/)).toBeVisible();
  await expect(page.locator(".photo-list li")).toHaveCount(0);
  await page.locator("#photo-files").setInputFiles(batch);
  await expect(
    page.getByRole("button", { name: "Cancel photo task" }),
  ).toHaveCount(0, { timeout: 120000 });
  await page.getByRole("button", { name: "Apply photos", exact: true }).click();
  await expect(page.getByText("Page 1 of 20", { exact: true })).toBeVisible({
    timeout: 60000,
  });
});
test("HEIC rejects twenty-one files and multi-photo containers, then accepts a 12MP photo", async ({
  page,
}) => {
  test.setTimeout(120000);
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await page
    .getByRole("button", { name: "Turn Photos into PDF", exact: true })
    .click();
  const buffer = await readFile("tests/fixtures/photos/synthetic.heic");
  await page.locator("#photo-files").setInputFiles(
    Array.from({ length: 21 }, (_, i) => ({
      name: `${i}.heic`,
      mimeType: "image/heic",
      buffer,
    })),
  );
  await expect(
    page.getByText("Use at most 20 images and 50 MiB in this photo task.", {
      exact: true,
    }),
  ).toBeVisible();
  await page
    .locator("#photo-files")
    .setInputFiles("tests/fixtures/photos/synthetic-multi.heic");
  await expect(
    page.getByText(/Multi-photo HEIC files are not supported/),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Remove image 1", exact: true })
    .click();
  await page
    .locator("#photo-files")
    .setInputFiles("tests/fixtures/photos/synthetic-12mp.heic");
  await expect(
    page.getByRole("button", { name: "Cancel photo task" }),
  ).toHaveCount(0, { timeout: 90000 });
  await page.getByRole("button", { name: "Apply photos", exact: true }).click();
  await expect(page.getByText("Page 1 of 1", { exact: true })).toBeVisible({
    timeout: 60000,
  });
});
