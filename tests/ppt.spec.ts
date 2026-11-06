import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { writeFile } from "node:fs/promises";
import { PDFDocument } from "pdf-lib";

const input = execFileSync(
  process.platform === "win32" ? "python" : "python3",
  [
    "-B",
    "-c",
    "import sys;sys.path.insert(0,'server/ppt');from synthetic import presentation;sys.stdout.buffer.write(presentation())",
  ],
);
const id = "11111111-1111-4111-8111-111111111111";
const selection = {
  name: "synthetic-slides.pptx",
  mimeType:
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  buffer: input,
};

test("PPT accepts a 32 MiB selection locally and refuses above 60 MiB without uploading", async ({
  page,
}, testInfo) => {
  let mutations = 0;
  await page.route("**/api/ppt/**", async (route) => {
    if (route.request().method() !== "GET") mutations++;
    return route.fulfill({
      json: {
        available: true,
        ready: true,
        mode: "local",
        region: "Synthetic",
        retentionMinutes: 60,
        maxBytes: 60 * 1024 ** 2,
      },
    });
  });
  const large = execFileSync(
    process.platform === "win32" ? "python" : "python3",
    [
      "-B",
      "-c",
      "import sys;sys.path.insert(0,'server/ppt');from synthetic import large_presentation;sys.stdout.buffer.write(large_presentation())",
    ],
    { maxBuffer: 40 * 1024 ** 2 },
  );
  await page.goto("/powerpoint-to-pdf/");
  await expect(
    page.getByText("One PPTX · up to 60 MiB · up to 200 visible slides", {
      exact: true,
    }),
  ).toBeVisible();
  await page
    .locator('input[type="file"]')
    .setInputFiles({ ...selection, buffer: large });
  await expect(
    page.getByRole("button", { name: "Upload and convert", exact: true }),
  ).toBeEnabled();
  expect(mutations).toBe(0);
  const oversized = testInfo.outputPath("synthetic-oversized.pptx");
  await writeFile(oversized, Buffer.alloc(60 * 1024 ** 2 + 1));
  await page.locator('input[type="file"]').setInputFiles(oversized);
  await expect(page.getByRole("alert")).toContainText("60 MiB");
  expect(mutations).toBe(0);
});

for (const width of [320, 390, 1280]) {
  test(`PPT ${width}: explicit upload, correct result download and a clean next task`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    const pdf = await PDFDocument.create();
    pdf.addPage([960, 540]);
    const bytes = Buffer.from(await pdf.save());
    let creates = 0,
      uploads = 0,
      deleted = false;
    await page.route("**/api/ppt/**", async (route) => {
      const request = route.request(),
        path = new URL(request.url()).pathname;
      const job = {
        id,
        state: deleted ? "cancelled" : "succeeded",
        pages: 1,
        warnings: [],
        cleanupPending: false,
      };
      if (path.endsWith("/session"))
        return route.fulfill({
          json: {
            available: true,
            region: "Local synthetic test service",
            retentionMinutes: 60,
            mode: "local",
          },
        });
      if (request.method() === "POST") {
        creates++;
        return route.fulfill({
          status: 201,
          json: { ...job, state: "created" },
        });
      }
      if (request.method() === "PUT") {
        uploads++;
        expect(request.headers()["content-type"]).toBe(selection.mimeType);
        // WebKit does not expose File-backed XHR bytes in intercepted requests.
        const posted = request.postDataBuffer();
        if (posted) expect(posted.equals(input)).toBe(true);
        return route.fulfill({
          status: 202,
          json: { ...job, state: "queued" },
        });
      }
      if (request.method() === "DELETE") {
        deleted = true;
        return route.fulfill({ json: { ...job, state: "cancelled" } });
      }
      if (path.endsWith("/result"))
        return route.fulfill({ contentType: "application/pdf", body: bytes });
      return route.fulfill({ json: job });
    });
    await page.goto("/powerpoint-to-pdf/");
    await expect(
      page.getByRole("heading", { name: "PowerPoint to PDF", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Upload and convert", exact: true }),
    ).toHaveCount(0);
    await page.locator('input[type="file"]').setInputFiles(selection);
    const convert = page.getByRole("button", {
      name: "Upload and convert",
      exact: true,
    });
    await expect(convert).toBeEnabled();
    expect(creates).toBe(0);
    expect(uploads).toBe(0);
    await page.screenshot({
      path: `.research/ppt/ui-selected-${width}-${test.info().project.name}.png`,
    });
    await convert.click();
    await expect(
      page.getByRole("heading", { name: "Your PDF is ready" }),
    ).toBeFocused();
    expect(creates).toBe(1);
    expect(uploads).toBe(1);
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("link", { name: "Download PDF", exact: true }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe("synthetic-slides.pdf");
    await page
      .getByRole("button", {
        name: "Delete files and convert another",
        exact: true,
      })
      .click();
    await expect(
      page.getByRole("heading", {
        name: "Drop your PowerPoint presentation here",
      }),
    ).toBeVisible();
    expect(deleted).toBe(true);
    await expect(
      page.getByRole("link", { name: "Download PDF", exact: true }),
    ).toHaveCount(0);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  });
}

test("PPT: invalid input recovery and cancellation suppress late results", async ({
  page,
}) => {
  let uploads = 0,
    cancelled = false;
  await page.route("**/api/ppt/**", async (route) => {
    const req = route.request();
    if (req.url().endsWith("/session"))
      return route.fulfill({
        json: { available: true, region: "Synthetic", retentionMinutes: 60 },
      });
    if (req.method() === "POST")
      return route.fulfill({
        status: 201,
        json: { id, state: "created", warnings: [] },
      });
    if (req.method() === "PUT") {
      uploads++;
      return route.fulfill({
        status: 202,
        json: { id, state: "queued", warnings: [] },
      });
    }
    if (req.method() === "DELETE") cancelled = true;
    return route.fulfill({
      json: {
        id,
        state: cancelled ? "cancelled" : "converting",
        cleanupPending: false,
        warnings: [],
      },
    });
  });
  await page.goto("/powerpoint-to-pdf/");
  await page.locator('input[type="file"]').setInputFiles({
    name: "broken.pptx",
    mimeType: selection.mimeType,
    buffer: Buffer.from("not a presentation"),
  });
  await expect(page.getByRole("alert")).toContainText("valid");
  expect(uploads).toBe(0);
  await page.locator('input[type="file"]').setInputFiles(selection);
  await page
    .getByRole("button", { name: "Upload and convert", exact: true })
    .click();
  await expect(
    page.getByText("Converting slides to PDF…", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Cancel conversion", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Drop your PowerPoint presentation here",
    }),
  ).toBeVisible();
  expect(cancelled).toBe(true);
  await expect(
    page.getByRole("link", { name: "Download PDF", exact: true }),
  ).toHaveCount(0);
});
