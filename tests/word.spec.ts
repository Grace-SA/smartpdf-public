import { test, expect, type Page } from "@playwright/test";
import { PDFDocument } from "pdf-lib";
import { docxFixture } from "./docx-fixture";

async function mockService(page: Page, mode = "success") {
  const pdf = await PDFDocument.create();
  pdf.addPage();
  const bytes = Buffer.from(await pdf.save());
  const calls: string[] = [];
  let uploaded = false;
  let cancelled = false;
  let options: unknown;
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
            capabilities: {
              revisionViews: ["final", "original"],
              omitComments: true,
            },
          });
    if (method === "DELETE") {
      if (mode === "cleanup-fails") return send(503, {});
      cancelled = true;
      return send(200, {
        id: "synthetic-task",
        state: "cancelled",
        cleanupPending: false,
        warnings: [],
      });
    }
    if (url.pathname.endsWith("/jobs")) {
      options = req.postDataJSON();
      if (mode === "proxy-html")
        return route.fulfill({
          status: 503,
          contentType: "text/html",
          body: "<h1>Unavailable</h1>",
        });
      return mode === "full"
        ? send(429, {
            error: "The conversion queue is full. Try again shortly.",
          })
        : send(201, { id: "synthetic-task", state: "created", warnings: [] });
    }
    if (url.pathname.endsWith("/input")) {
      if (mode === "upload-type") return send(415, {});
      uploaded = true;
      return send(202, { state: "queued" });
    }
    if (url.pathname.endsWith("/result"))
      return route.fulfill({
        status: 200,
        contentType: "application/pdf",
        body: mode === "invalid-pdf" ? Buffer.from("not pdf") : bytes,
      });
    return send(200, {
      id: "synthetic-task",
      state: cancelled
        ? "cancelled"
        : ["reject", "cleanup-fails", "engine-start"].includes(mode)
          ? "failed"
          : mode === "slow" || !uploaded
            ? "starting"
            : "succeeded",
      options,
      pages: 1,
      warnings: ["Fonts may be substituted. Check pagination before sharing."],
      ...(["reject", "cleanup-fails", "engine-start"].includes(mode)
        ? {
            failureCode:
              mode === "engine-start"
                ? "ENGINE_STARTUP_FAILED"
                : "INPUT_REJECTED",
            error:
              "Accept or reject tracked changes in Word before converting.",
          }
        : {}),
    });
  });
  return calls;
}
async function select(
  page: Page,
  name = "Synthetic report.docx",
  buffer = docxFixture(),
) {
  await page.locator("#word-file").setInputFiles({
    name,
    mimeType:
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    buffer,
  });
}

for (const width of [320, 390, 1280]) {
  test(`${width}: selection is the first primary action, conversion appears after local selection`, async ({
    page,
  }, info) => {
    const calls = await mockService(page);
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/word-to-pdf/");
    const picker = page.locator('.word-dropzone label[for="word-file"]');
    await expect(picker).toBeVisible();
    expect((await picker.boundingBox())!.height).toBeGreaterThanOrEqual(60);
    await expect(
      page.getByRole("button", { name: "Upload and convert", exact: true }),
    ).toHaveCount(0);
    const chooser = page.waitForEvent("filechooser", { timeout: 5000 });
    await page.locator("#word-file").click();
    await (await chooser).setFiles([]);
    await page.screenshot({ path: info.outputPath(`word-empty-${width}.png`) });
    await select(page);
    await expect(page.locator(".word-dropzone")).toHaveCount(0);
    await expect(page.locator(".word-selected")).toContainText(
      "not uploaded yet",
    );
    await expect(
      page.getByRole("button", { name: "Upload and convert", exact: true }),
    ).toBeEnabled();
    await expect(page.locator('label[for="word-file"]')).toHaveText(
      "Change document",
    );
    expect(
      calls.some((call) => call.startsWith("POST") || call.startsWith("PUT")),
    ).toBe(false);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: info.outputPath(`word-selected-${width}.png`),
    });
  });
}

test("dropping a document selects locally and changing it does not start an upload", async ({
  page,
}) => {
  const calls = await mockService(page);
  await page.goto("/word-to-pdf/");
  const transfer = await page.evaluateHandle((bytes) => {
    const data = new DataTransfer();
    data.items.add(
      new File([new Uint8Array(bytes)], "Dropped.docx", {
        type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      }),
    );
    return data;
  }, Array.from(docxFixture()));
  await page
    .locator(".word-card")
    .dispatchEvent("dragover", { dataTransfer: transfer });
  await expect(page.locator(".word-card")).toHaveClass(/is-dragging/);
  await page
    .locator(".word-card")
    .dispatchEvent("drop", { dataTransfer: transfer });
  await expect(page.locator(".word-selected")).toContainText("Dropped.docx");
  await expect(page.locator(".word-card")).not.toHaveClass(/is-dragging/);
  await select(page, "Replacement.docx");
  await expect(page.locator(".word-selected")).toContainText(
    "Replacement.docx",
  );
  expect(
    calls.some((call) => call.startsWith("POST") || call.startsWith("PUT")),
  ).toBe(false);
});
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
  await expect(page.getByRole("alert")).toContainText(
    "Accept or reject tracked changes",
  );
  await expect(
    page.getByRole("button", { name: "Upload and convert" }),
  ).toBeDisabled();
});
test("local preflight refuses invalid or unresolved documents before any upload", async ({
  page,
}) => {
  const calls = await mockService(page);
  await page.goto("/word-to-pdf/");
  await select(page, "Broken.docx", Buffer.from("not a package"));
  await expect(page.getByRole("alert")).toContainText(
    "valid, unencrypted DOCX",
  );
  await expect(
    page.getByRole("button", { name: "Upload and convert", exact: true }),
  ).toBeDisabled();
  await select(
    page,
    "Revisions.docx",
    docxFixture("<w:p><w:ins><w:r><w:t>Inserted</w:t></w:r></w:ins></w:p>"),
  );
  await expect(page.getByRole("alert")).toContainText("tracked changes");
  expect(calls.some((c) => c.startsWith("POST") || c.startsWith("PUT"))).toBe(
    false,
  );
  await select(
    page,
    "Visible.docx",
    docxFixture(
      '<w:p><w:r><w:rPr><w:webHidden/><w:vanish w:val="false"/></w:rPr><w:t>Visible</w:t></w:r></w:p>',
    ),
  );
  await expect(
    page.getByRole("button", { name: "Upload and convert", exact: true }),
  ).toBeEnabled();
  expect(calls.some((c) => c.startsWith("POST") || c.startsWith("PUT"))).toBe(
    false,
  );
});

test("revision and comment choices are explicit, local, and reset for a new file", async ({
  page,
}) => {
  const calls = await mockService(page);
  await page.goto("/word-to-pdf/");
  const fixture = docxFixture(
    "<w:p><w:ins><w:r><w:t>Inserted</w:t></w:r></w:ins><w:commentRangeStart/></w:p>",
  );
  await select(page, "Review.docx", fixture);
  const convert = page.getByRole("button", {
    name: "Upload and convert",
    exact: true,
  });
  await expect(
    page.getByLabel("Tracked changes", { exact: true }),
  ).toBeVisible();
  await expect(convert).toBeDisabled();
  await page
    .getByLabel("Tracked changes", { exact: true })
    .selectOption("original");
  await expect(convert).toBeDisabled();
  await page
    .getByRole("checkbox", { name: "Create the PDF without comments" })
    .check();
  await expect(convert).toBeEnabled();
  expect(calls.some((x) => x.startsWith("POST") || x.startsWith("PUT"))).toBe(
    false,
  );
  await select(page, "Other.docx", fixture);
  await expect(page.getByLabel("Tracked changes", { exact: true })).toHaveValue(
    "unchanged",
  );
  await expect(
    page.getByRole("checkbox", { name: "Create the PDF without comments" }),
  ).not.toBeChecked();
  await expect(convert).toBeDisabled();
});
test("original formatting history is not offered as a misleading original view", async ({
  page,
}) => {
  await mockService(page);
  await page.goto("/word-to-pdf/");
  await select(
    page,
    "Format changes.docx",
    docxFixture(
      "<w:p><w:pPr><w:pPrChange><w:pPr/></w:pPrChange></w:pPr><w:r><w:t>Text</w:t></w:r></w:p>",
    ),
  );
  await expect(
    page.getByText(
      "To restore this document’s original formatting or structure, export from Word. Current content is available here.",
    ),
  ).toBeVisible();
  await page
    .getByLabel("Tracked changes", { exact: true })
    .selectOption("final");
  await expect(
    page.getByRole("button", { name: "Upload and convert", exact: true }),
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

for (const [mode, message] of [
  ["proxy-html", "temporarily unavailable"],
  ["upload-type", "Choose a DOCX"],
  ["invalid-pdf", "failed its checks"],
  ["engine-start", "could not start"],
]) {
  test(`specific recoverable failure: ${mode}`, async ({ page }) => {
    await mockService(page, mode);
    await page.goto("/word-to-pdf/");
    await select(page);
    await page
      .getByRole("button", { name: "Upload and convert", exact: true })
      .click();
    await expect(page.getByRole("alert")).toContainText(message!);
    await expect(
      page.getByRole("button", { name: "Upload and convert", exact: true }),
    ).toBeEnabled();
    await expect(
      page.getByRole("link", { name: "Download PDF", exact: true }),
    ).toHaveCount(0);
  });
}
test("uncertain cleanup blocks another upload until deletion succeeds", async ({
  page,
}) => {
  const calls = await mockService(page, "cleanup-fails");
  await page.goto("/word-to-pdf/");
  await select(page);
  await page
    .getByRole("button", { name: "Upload and convert", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "cleanup could not be confirmed",
  );
  await expect(
    page.getByRole("button", { name: "Upload and convert", exact: true }),
  ).toBeDisabled();
  expect(calls.filter((x) => x.startsWith("POST"))).toHaveLength(1);
  await page.unrouteAll();
  await mockService(page);
  await page
    .getByRole("button", { name: "Delete temporary files", exact: true })
    .click();
  await expect(
    page.getByText("Temporary files deleted. Your original is unchanged."),
  ).toBeVisible();
});
test("chosen content reaches only the explicitly started task", async ({
  page,
}) => {
  await mockService(page);
  await page.goto("/word-to-pdf/");
  await select(
    page,
    "Tracked.docx",
    docxFixture("<w:p><w:ins><w:r><w:t>New</w:t></w:r></w:ins></w:p>"),
  );
  await page
    .getByLabel("Tracked changes", { exact: true })
    .selectOption("original");
  const created = page.waitForRequest(
    (req) => req.method() === "POST" && req.url().endsWith("/api/word/jobs"),
  );
  await page
    .getByRole("button", { name: "Upload and convert", exact: true })
    .click();
  expect((await created).postDataJSON()).toEqual({
    revisionView: "original",
    omitComments: false,
  });
  await expect(
    page.getByText("PDF content: original content (tracked changes rejected)."),
  ).toBeVisible();
});
