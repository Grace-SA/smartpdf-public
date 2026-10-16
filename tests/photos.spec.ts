import { test, expect, type Page } from "@playwright/test";
import { readFile, mkdir } from "node:fs/promises";
import { PDFDocument } from "pdf-lib";
import { writeFile } from "node:fs/promises";
async function open(page: Page) {
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await page
    .getByRole("button", { name: "Turn Photos into PDF", exact: true })
    .click();
}
async function add(page: Page, names: string[]) {
  await page
    .locator("#photo-files")
    .setInputFiles(names.map((n) => `tests/fixtures/photos/${n}`));
  await expect(
    page.getByRole("button", { name: "Apply photos", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Cancel photo task" }),
  ).toHaveCount(0);
}
test("PHOTO-01 offline reorder rotate remove apply preview save undo redo", async ({
  page,
  context,
  browserName,
}) => {
  await open(page);
  // Windows WebKit's synthetic offline flag prevents even local FileReader
  // operations. Deny HTTP requests while preserving local-file I/O instead.
  if (browserName === "webkit")
    await context.route(/^https?:/, (route) => route.abort());
  else await context.setOffline(true);
  const requests: string[] = [];
  page.on("request", (r) => {
    if (/^https?:/.test(r.url())) requests.push(r.url());
  });
  let downloads = 0;
  page.on("download", () => downloads++);
  await add(page, [
    "red.jpg",
    "alpha.png",
    "green.jpg",
    "blue.jpg",
    "corners.png",
  ]);
  await page
    .getByRole("button", { name: "Move image 5 up", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Rotate image 2", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Remove image 3", exact: true })
    .click();
  await page.getByLabel("PDF name", { exact: true }).fill("测试/照片");
  await page.getByRole("button", { name: "Apply photos", exact: true }).click();
  await expect(page.getByText("Page 1 of 4", { exact: true })).toBeVisible();
  expect(downloads).toBe(0);
  await page.getByRole("button", { name: "Next", exact: false }).click();
  await expect(page.getByText("Page 2 of 4", { exact: true })).toBeVisible();
  const dl = page.waitForEvent("download");
  await page.getByRole("button", { name: "Save PDF", exact: true }).click();
  const download = await dl;
  expect(download.suggestedFilename()).toBe("测试_照片.pdf");
  await mkdir("docs/private-samples/m1", { recursive: true });
  await download.saveAs("docs/private-samples/m1/photo01-browser.pdf");
  const doc = await PDFDocument.load(
    await readFile("docs/private-samples/m1/photo01-browser.pdf"),
  );
  expect(doc.getPageCount()).toBe(4);
  await expect(
    page.getByRole("alert").filter({ hasText: "Download started" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Undo Create Photos PDF", exact: true })
    .click();
  await expect(page.locator("canvas")).toHaveCount(0);
  await page
    .getByRole("button", { name: "Redo Create Photos PDF", exact: true })
    .click();
  await expect(page.getByText("Page 1 of 4", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Clear session", exact: true })
    .click();
  await page.getByRole("button", { name: "End session", exact: true }).click();
  await expect(page.locator("canvas")).toHaveCount(0);
  expect(requests).toEqual([]);
  expect(
    await page.evaluate(async () => [
      localStorage.length,
      sessionStorage.length,
      (await indexedDB.databases()).length,
      (await caches.keys()).length,
    ]),
  ).toEqual([0, 0, 0, 0]);
});
test("PHOTO-03 invalid item, draft choice and cancellation preserve prior PDF", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await page.locator("#pdf-file").setInputFiles("tests/fixtures/plain.pdf");
  await expect(page.locator(".canvas-host canvas")).toBeVisible();
  await page
    .getByRole("button", { name: "Turn Photos into PDF", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Apply photos", exact: true }),
  ).toBeDisabled();
  await page.locator("#photo-files").setInputFiles([
    {
      name: "bad.jpg",
      mimeType: "image/jpeg",
      buffer: Buffer.from("not an image"),
    },
  ]);
  await expect(
    page.getByRole("alert").filter({ hasText: "Remove this image" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Apply photos", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Remove image 1", exact: true })
    .click();
  await add(page, ["red.jpg"]);
  await page
    .getByRole("button", { name: "Back to PDF preview", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Unapplied photo changes" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Stay here", exact: true }).click();
  await expect(page.locator(".photo-list li")).toHaveCount(1);
  await page
    .getByRole("button", { name: "Back to PDF preview", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Discard changes", exact: true })
    .click();
  await expect(page.getByText("Page 1 of 2", { exact: true })).toBeVisible();
  await expect(page.locator("#photo-files")).toHaveCount(0);
});
test("ten photo revisions undo and redo without replacing originals; branch confirmation", async ({
  page,
}) => {
  await open(page);
  for (let n = 0; n < 10; n++) {
    await add(page, ["red.jpg"]);
    if (n) await page.getByRole("checkbox", { name: /Replace/ }).check();
    await page
      .getByRole("button", { name: "Apply photos", exact: true })
      .click();
    await expect(
      page.getByRole("alert").filter({ hasText: "Created 1 pages" }),
    ).toBeVisible();
  }
  for (let n = 0; n < 10; n++) {
    await page
      .getByRole("button", { name: "Undo Create Photos PDF", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Cancel", exact: true }),
    ).toHaveCount(0);
  }
  await expect(page.locator("canvas")).toHaveCount(0);
  await page
    .getByRole("button", { name: "Redo Create Photos PDF", exact: true })
    .click();
  await expect(page.locator(".canvas-host canvas")).toBeVisible();
  await add(page, ["blue.jpg"]);
  await page.getByRole("checkbox", { name: /Replace/ }).check();
  await page.getByRole("button", { name: "Apply photos", exact: true }).click();
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: "Confirm that applying will discard" }),
  ).toBeVisible();
  await page.getByRole("checkbox", { name: /Discard the redo branch/ }).check();
  await page.getByRole("button", { name: "Apply photos", exact: true }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "Created 1 pages" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /^Redo/ })).toBeDisabled();
});
test("photo task is cancellable before a delayed worker result", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const Native = Worker;
    window.Worker = class extends Native {
      postMessage(
        data: unknown,
        options?: StructuredSerializeOptions | Transferable[],
      ) {
        if (data && typeof data === "object" && "inputs" in data) return;
        super.postMessage(
          data,
          Array.isArray(options) ? { transfer: options } : options,
        );
      }
    };
  });
  await open(page);
  await add(page, ["red.jpg"]);
  await page.getByRole("button", { name: "Apply photos", exact: true }).click();
  await page
    .getByRole("button", { name: "Cancel photo task", exact: true })
    .click();
  await expect(
    page.getByRole("alert").filter({ hasText: "Cancelled" }),
  ).toBeVisible();
  await expect(page.locator("canvas")).toHaveCount(0);
  await expect(page.locator(".photo-list li")).toHaveCount(1);
});
test("photo controls fit small mobile width", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 780 });
  await open(page);
  await add(page, ["alpha.png"]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "docs/evidence/m1-mobile-layout.png",
    fullPage: true,
  });
});

test("apply-and-continue undo uses the new revision and stays on the previous document", async ({
  page,
}) => {
  await open(page);
  await add(page, ["red.jpg"]);
  await page.getByRole("button", { name: "Apply photos", exact: true }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "Created 1 pages" }),
  ).toBeVisible();
  await add(page, ["blue.jpg"]);
  await page.getByRole("checkbox", { name: /Replace/ }).check();
  await page
    .getByRole("button", { name: "Undo Create Photos PDF", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Apply and continue", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Unapplied photo changes" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Redo Create Photos PDF", exact: true }),
  ).toBeEnabled();
  const colour = await page
    .locator(".canvas-host canvas")
    .evaluate((c: HTMLCanvasElement) =>
      Array.from(
        c.getContext("2d")!.getImageData(c.width / 2, c.height / 2, 1, 1).data,
      ),
    );
  expect(colour[0]).toBeGreaterThan(240);
  expect(colour[2]).toBeLessThan(15);
});

test("M1 ten 2MP photos benchmark and repeated clear release worker and URL resources", async ({
  page,
  browser,
}) => {
  test.setTimeout(180000);
  await page.addInitScript(() => {
    const Native = Worker,
      workers = new Set<Worker>(),
      urls = new Set<string>();
    window.Worker = class extends Native {
      constructor(url: string | URL, options?: WorkerOptions) {
        super(url, options);
        workers.add(this);
      }
      terminate() {
        workers.delete(this);
        super.terminate();
      }
    };
    const create = URL.createObjectURL,
      revoke = URL.revokeObjectURL;
    URL.createObjectURL = (blob) => {
      const url = create(blob);
      if ("type" in blob && !blob.type.startsWith("text/javascript"))
        urls.add(url);
      return url;
    };
    URL.revokeObjectURL = (url) => {
      urls.delete(url);
      revoke(url);
    };
    Reflect.set(window, "__photoCounts", () => ({
      workers: workers.size,
      urls: urls.size,
    }));
  });
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  const buffer = await readFile("tests/fixtures/photos/benchmark-2mp.jpg");
  const times: number[] = [];
  for (let n = 0; n < 22; n++) {
    await page
      .getByRole("button", { name: "Turn Photos into PDF", exact: true })
      .click();
    await page.locator("#photo-files").setInputFiles(
      Array.from({ length: 10 }, (_, i) => ({
        name: `photo-${i}.jpg`,
        mimeType: "image/jpeg",
        buffer,
      })),
    );
    await expect(
      page.getByRole("button", { name: "Apply photos", exact: true }),
    ).toBeEnabled();
    const start = performance.now();
    await page
      .getByRole("button", { name: "Apply photos", exact: true })
      .click();
    await expect(
      page.getByRole("alert").filter({ hasText: "Created 10 pages" }),
    ).toBeVisible();
    if (n >= 2) times.push(performance.now() - start);
    await page
      .getByRole("button", { name: "Clear session", exact: true })
      .click();
    await page
      .getByRole("button", { name: "End session", exact: true })
      .click();
    await expect
      .poll(() => page.evaluate(() => Reflect.get(window, "__photoCounts")()))
      .toEqual({ workers: 0, urls: 0 });
  }
  const p95 = [...times].sort((a, b) => a - b)[18]!;
  expect(p95).toBeLessThanOrEqual(10000);
  await writeFile(
    "docs/evidence/m1-photo-baseline.json",
    JSON.stringify(
      {
        browser: browser.version(),
        environment: "Windows desktop, not phone",
        images: 10,
        pixelsEach: 2000000,
        warmups: 2,
        samples: times,
        p95Ms: p95,
        clearedCycles: 22,
      },
      null,
      2,
    ),
  );
});
