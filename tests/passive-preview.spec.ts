import { expect, test } from "@playwright/test";
import { passiveFixture } from "./passive-fixture";
import { makeFixture } from "./fixtures";

test("tagged and standard PDFs preview offline with clear limits; missing references preserve the old page", async ({
  page,
  context,
  browserName,
}) => {
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  if (browserName === "webkit")
    await context.route(/^https?:/, (route) => route.abort());
  else await context.setOffline(true);
  for (const kind of ["tagged", "pdfa", "pdfx"] as const) {
    await page.locator("#pdf-file").setInputFiles({
      name: `${kind}.pdf`,
      mimeType: "application/pdf",
      buffer: Buffer.from(await makeFixture(kind)),
    });
    await expect(page.getByText("Page 1 of 2", { exact: true })).toBeVisible();
    await expect(
      page.getByRole("note").filter({ hasText: "Page preview only" }),
    ).toContainText("not verified");
    await page.getByRole("button", { name: "Next" }).click();
    await expect(page.getByText("Page 2 of 2", { exact: true })).toBeVisible();
  }
  await page.locator("#pdf-file").setInputFiles({
    name: "missing.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from(await makeFixture("broken-ref")),
  });
  await expect(page.getByRole("alert")).toContainText(
    "object we could not read",
  );
  await expect(page.getByText("Page 2 of 2", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Clear session" }).click();
  await expect(page.locator("canvas")).toHaveCount(0);
});

test("passive links never navigate, default hidden layers stay hidden", async ({
  page,
  context,
  browserName,
}) => {
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  const requests: string[] = [];
  page.on("request", (request) => {
    if (!request.url().startsWith("blob:")) requests.push(request.url());
  });
  // WebKit's Windows automation offline switch also blocks local Blob reads.
  if (browserName === "webkit")
    await context.route(/^https?:/, (route) => route.abort());
  else await context.setOffline(true);
  await page.locator("#pdf-file").setInputFiles({
    name: "passive.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from(await (await passiveFixture()).save()),
  });
  await expect(page.getByText("Page 1 of 1", { exact: true })).toBeVisible();
  await expect(page.getByRole("note")).toContainText("not interactive");
  const pixels = await page
    .locator("canvas")
    .evaluate((canvas: HTMLCanvasElement) => {
      const ctx = canvas.getContext("2d")!;
      return [75, 225].map((x) =>
        Array.from(
          ctx.getImageData(
            Math.floor((x * canvas.width) / 400),
            Math.floor((150 * canvas.height) / 800),
            1,
            1,
          ).data,
        ),
      );
    });
  expect(pixels).toEqual([
    [0, 255, 0, 255],
    [255, 255, 255, 255],
  ]);
  const box = (await page.locator("canvas").boundingBox())!;
  await page.locator("canvas").click({
    position: { x: (box.width * 75) / 400, y: (box.height * 150) / 800 },
  });
  expect(context.pages()).toHaveLength(1);
  expect(page.url()).toBe("http://127.0.0.1:4185/");
  expect(requests).toEqual([]);
  expect(
    await page
      .locator(".preview a, .annotationLayer, iframe, embed, object")
      .count(),
  ).toBe(0);
});
