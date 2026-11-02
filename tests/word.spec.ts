import { test, expect, type Page } from "@playwright/test";
import { PDFDocument } from "pdf-lib";

async function mockService(page: Page, mode = "success") {
  const pdf = await PDFDocument.create();
  pdf.addPage();
  const bytes = Buffer.from(await pdf.save());
  const calls: string[] = [];
  let uploaded = false;
  let cancelled = false;
  await page.route("**/api/word/**", async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const method = req.method();
    calls.push(method + " " + url.pathname);
    const send = (status: number, value: unknown) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(value),
      });
    if (url.pathname.endsWith("/session"))
      return mode === "offline"
        ? send(503, {})
        : send(200, {
            region: "Local acceptance server",
            available: true,
            retentionMinutes: 60,
          });
    if (method === "DELETE") {
      cancelled = true;
      return send(200, {
        id: "synthetic-task",
        state: "cancelled",
        cleanupPending: false,
        warnings: [],
      });
    }
    if (url.pathname.endsWith("/jobs"))
      return mode === "full"
        ? send(429, {
            error: "The conversion queue is full. Try again shortly.",
          })
        : send(201, { id: "synthetic-task", state: "created", warnings: [] });
    if (url.pathname.endsWith("/input")) {
      uploaded = true;
      return send(202, { state: "queued" });
    }
    if (url.pathname.endsWith("/result"))
      return route.fulfill({
        status: 200,
        contentType: "application/pdf",
        body: bytes,
      });
    return send(200, {
      id: "synthetic-task",
      state: cancelled
        ? "cancelled"
        : mode === "reject"
          ? "failed"
          : mode === "slow" || !uploaded
            ? "starting"
            : "succeeded",
      pages: 1,
      warnings: ["Fonts may be substituted. Check pagination before sharing."],
      ...(mode === "reject"
        ? {
            error:
              "Resolve revisions, comments, hidden content or embedded objects in Word first.",
          }
        : {}),
    });
  });
  return calls;
}
async function select(
  page: Page,
  name = "Synthetic report.docx",
  buffer = Buffer.from("synthetic test input"),
) {
  await page.locator("#word-file").setInputFiles({
    name,
    mimeType:
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    buffer,
  });
}
test("selection stays local until explicit start, then preview and download work", async ({
  page,
}) => {
  const calls = await mockService(page);
  await page.goto("/word-to-pdf/");
  await expect(
    page.getByRole("heading", { name: "Word to PDF", exact: true, level: 1 }),
  ).toBeVisible();
  await expect(page.getByRole("note")).toContainText("uploaded only when");
  await select(page);
  expect(
    calls.filter((c) => c.startsWith("PUT") || c.startsWith("POST")),
  ).toHaveLength(0);
  await page
    .getByRole("button", { name: "Upload and convert", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your PDF is ready" }),
  ).toBeVisible();
  await expect(
    page.getByText("1 page · Check the layout before sharing."),
  ).toBeVisible();
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download PDF", exact: true }).click();
  // Linux WebKit normalizes spaces in native download names to underscores.
  expect(["Synthetic report.pdf", "Synthetic_report.pdf"]).toContain(
    (await downloadEvent).suggestedFilename(),
  );
  await page.getByRole("button", { name: "Preview PDF", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page
    .getByRole("button", { name: "Close preview", exact: true })
    .click();
  await page.getByRole("button", { name: "Delete temporary files" }).click();
  await expect(
    page.getByText("Temporary files deleted. Your original is unchanged."),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "Download PDF" })).toHaveCount(0);
});
test("cancelling a running conversion removes access without late success", async ({
  page,
}) => {
  const calls = await mockService(page, "slow");
  await page.goto("/word-to-pdf/");
  await select(page);
  await page.getByRole("button", { name: "Upload and convert" }).click();
  await expect(page.getByText("Preparing your conversion…")).toBeVisible();
  await page.getByRole("button", { name: "Cancel conversion" }).click();
  await expect(
    page.getByText("Temporary files deleted. Your original is unchanged."),
  ).toBeVisible();
  expect(calls.some((call) => call.startsWith("DELETE"))).toBe(true);
  await expect(
    page.getByRole("heading", { name: "Your PDF is ready" }),
  ).toHaveCount(0);
});
test("local file errors do not upload; rejected documents offer a clear next step", async ({
  page,
}) => {
  const calls = await mockService(page, "reject");
  await page.goto("/word-to-pdf/");
  await select(page, "old.doc");
  await expect(page.getByRole("alert")).toContainText("Save older .doc files");
  await select(page, "empty.docx", Buffer.alloc(0));
  await expect(page.getByRole("alert")).toContainText("non-empty DOCX");
  expect(calls.some((call) => call.startsWith("PUT"))).toBe(false);
  await select(page);
  await page.getByRole("button", { name: "Upload and convert" }).click();
  await expect(page.getByRole("alert")).toContainText("Resolve revisions");
  await expect(
    page.getByRole("button", { name: "Upload and convert" }),
  ).toBeEnabled();
});
test("queue full and disconnected service remain recoverable", async ({
  page,
}) => {
  await mockService(page, "full");
  await page.goto("/word-to-pdf/");
  await select(page);
  await page.getByRole("button", { name: "Upload and convert" }).click();
  await expect(page.getByRole("alert")).toContainText("queue is full");
  await page.unrouteAll();
  await mockService(page, "offline");
  await page.reload();
  await expect(page.getByRole("alert")).toContainText("has not been uploaded");
  await expect(
    page.getByRole("button", { name: "Retry connection" }),
  ).toBeEnabled();
});
test("home exposes cloud tool and phone layout remains bounded", async ({
  page,
}) => {
  await mockService(page);
  await page.goto("/");
  await page.locator('.tool-cards a[href="/word-to-pdf/"]').click();
  await expect(page).toHaveURL(/\/word-to-pdf\/$/);
  await page.setViewportSize({ width: 320, height: 760 });
  await select(page, "Synthetic-".repeat(20) + ".docx");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await expect(
    page.getByRole("note").getByText("Cloud conversion", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("No file or filename upload", { exact: true }),
  ).toHaveCount(0);
});

test("a missing Word tool chunk offers recovery instead of an empty page", async ({
  page,
}) => {
  await page.route("**/assets/WordPage-*.js", (route) => route.abort());
  await page.goto("/word-to-pdf/");
  await expect(
    page.getByRole("button", {
      name: "Retry opening Word to PDF",
      exact: true,
    }),
  ).toBeVisible();
  await page.unroute("**/assets/WordPage-*.js");
  await page
    .getByRole("button", { name: "Retry opening Word to PDF", exact: true })
    .click();
  await expect(page.locator("#word-file")).toBeVisible();
});

test("leaving a selected Word task offers keep or discard", async ({
  page,
}) => {
  await mockService(page);
  await page.goto("/word-to-pdf/");
  await select(page);
  await page.getByRole("link", { name: "← All tools", exact: true }).click();
  await expect(
    page.getByRole("dialog", { name: "Leave this task?" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Keep editing", exact: true }).click();
  await expect(
    page.getByText("Synthetic report.docx ·", { exact: false }),
  ).toBeVisible();
  await page.getByRole("link", { name: "← All tools", exact: true }).click();
  await page
    .getByRole("button", { name: "Discard task and leave", exact: true })
    .click();
  await expect(page).toHaveURL(/\/$/);
  await expect(
    page.getByRole("heading", {
      name: "Simple PDF tools. Clear choices for your files.",
      exact: true,
    }),
  ).toBeVisible();
});
