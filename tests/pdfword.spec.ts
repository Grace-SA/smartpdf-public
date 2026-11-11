import { expect, test } from "@playwright/test";

const input = Buffer.from("%PDF-1.7\nSynthetic local signature check");
const id = "11111111-1111-4111-8111-111111111111";
const selection = {
  name: "synthetic-text.pdf",
  mimeType: "application/pdf",
  buffer: input,
};

for (const width of [320, 390, 1280]) {
  test(`PDF to Word ${width}: explicit upload, correct result download and a clean next task`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    const bytes = Buffer.from("PKsynthetic-validated-by-service");
    let creates = 0,
      uploads = 0,
      deleted = false;
    await page.route("**/api/pdfword/**", async (route) => {
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
        return route.fulfill({
          contentType:
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          body: bytes,
        });
      return route.fulfill({ json: job });
    });
    await page.goto("/pdf-to-word/");
    await expect(
      page.getByRole("heading", { name: "PDF to Word", exact: true }),
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
    const selectionBox = await page
      .locator(".word-selected .word-selection-copy")
      .boundingBox();
    expect(selectionBox!.width).toBeGreaterThan(140);
    expect(selectionBox!.height).toBeLessThan(130);
    expect(creates).toBe(0);
    expect(uploads).toBe(0);
    await page.screenshot({
      path: `.research/pdfword/ui-selected-${width}-${test.info().project.name}.png`,
    });
    await convert.click();
    await expect(
      page.getByRole("heading", { name: "Your Word document is ready" }),
    ).toBeFocused();
    expect(creates).toBe(1);
    expect(uploads).toBe(1);
    const downloadPromise = page.waitForEvent("download");
    await page
      .getByRole("link", { name: "Download Word", exact: true })
      .click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe("synthetic-text.docx");
    await page
      .getByRole("button", {
        name: "Delete files and convert another",
        exact: true,
      })
      .click();
    await expect(
      page.getByRole("heading", {
        name: "Drop your PDF here",
      }),
    ).toBeVisible();
    expect(deleted).toBe(true);
    await expect(
      page.getByRole("link", { name: "Download Word", exact: true }),
    ).toHaveCount(0);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  });
}

test("PDF to Word: invalid input recovery and cancellation suppress late results", async ({
  page,
}) => {
  let uploads = 0,
    cancelled = false;
  await page.route("**/api/pdfword/**", async (route) => {
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
  await page.goto("/pdf-to-word/");
  await page.locator('input[type="file"]').setInputFiles({
    name: "broken.pdf",
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
    page.getByText("Creating editable Word text…", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Cancel conversion", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Drop your PDF here",
    }),
  ).toBeVisible();
  expect(cancelled).toBe(true);
  await expect(
    page.getByRole("link", { name: "Download Word", exact: true }),
  ).toHaveCount(0);
});

test("cancelling during job creation waits for its ID and deletes it without uploading", async ({
  page,
}) => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  let creating = false,
    deleted = false,
    uploads = 0;
  await page.route("**/api/pdfword/**", async (route) => {
    const req = route.request();
    if (req.url().endsWith("/session"))
      return route.fulfill({
        json: {
          available: true,
          region: "Synthetic local",
          retentionMinutes: 60,
        },
      });
    if (req.method() === "POST") {
      creating = true;
      await gate;
      return route.fulfill({
        status: 201,
        json: { id, state: "created", warnings: [] },
      });
    }
    if (req.method() === "PUT") uploads++;
    if (req.method() === "DELETE") deleted = true;
    return route.fulfill({
      json: {
        id,
        state: deleted ? "cancelled" : "created",
        cleanupPending: false,
        warnings: [],
      },
    });
  });
  await page.goto("/pdf-to-word/");
  await page.locator('input[type="file"]').setInputFiles(selection);
  await page
    .getByRole("button", { name: "Upload and convert", exact: true })
    .click();
  await expect.poll(() => creating).toBe(true);
  await page
    .getByRole("button", { name: "Cancel conversion", exact: true })
    .click();
  await expect(
    page.getByText("Deleting temporary files…", { exact: true }),
  ).toBeVisible();
  release();
  await expect(
    page.getByRole("heading", { name: "Drop your PDF here" }),
  ).toBeVisible();
  expect(deleted).toBe(true);
  expect(uploads).toBe(0);
});
