import { test, expect } from "@playwright/test";
import { readFile, mkdir } from "node:fs/promises";
test.skip(
  process.env.SMARTWORKS_PRIVATE_HEIC !== "1",
  "Explicit local private-sample run only",
);
test("local private iPhone gain-map HEIC converts to an SDR PDF without network requests", async ({
  page,
}, info) => {
  test.setTimeout(90000);
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await page
    .getByRole("button", { name: "Turn Photos into PDF", exact: true })
    .click();
  const requests: string[] = [];
  await page.route(/^https?:/, (route) => {
    requests.push(route.request().url());
    return route.abort();
  });
  await page
    .locator("#photo-browse-files")
    .setInputFiles("docs/private-samples/heic/real-hdr.heic");
  await expect(
    page.getByText(
      "HDR photo: the PDF uses its standard-brightness image. HDR screen highlights are not retained.",
      { exact: true },
    ),
  ).toBeVisible({ timeout: 60000 });
  await expect(
    page.getByRole("button", { name: "Apply photos", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Apply photos", exact: true }).click();
  await expect(page.getByText("Page 1 of 1", { exact: true })).toBeVisible({
    timeout: 30000,
  });
  const saved = page.waitForEvent("download");
  await page.getByRole("button", { name: "Save PDF", exact: true }).click();
  await mkdir("docs/private-samples/heic", { recursive: true });
  await (
    await saved
  ).saveAs(`docs/private-samples/heic/real-hdr-${info.project.name}.pdf`);
  expect(requests).toEqual([]);
});
test("one original HDR HEIC plus nineteen images produces twenty pages", async ({
  page,
}) => {
  test.setTimeout(90000);
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await page
    .getByRole("button", { name: "Turn Photos into PDF", exact: true })
    .click();
  const original = await readFile("docs/private-samples/heic/real-hdr.heic"),
    synthetic = await readFile("tests/fixtures/photos/synthetic.heic");
  await page.locator("#photo-browse-files").setInputFiles(
    Array.from({ length: 20 }, (_, i) => ({
      name: `local-${i}.heic`,
      mimeType: "image/heic",
      buffer: i === 0 ? original : synthetic,
    })),
  );
  await expect(
    page.getByRole("button", { name: "Apply photos", exact: true }),
  ).toBeEnabled({ timeout: 60000 });
  await page.getByRole("button", { name: "Apply photos", exact: true }).click();
  await expect(page.getByText("Page 1 of 20", { exact: true })).toBeVisible({
    timeout: 30000,
  });
});
