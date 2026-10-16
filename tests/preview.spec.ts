import { test, expect } from "@playwright/test";
import { makeFixture } from "./fixtures";
import { writeFile } from "node:fs/promises";
const upload = async (
  page: import("@playwright/test").Page,
  kind: Parameters<typeof makeFixture>[0] = "plain",
  name = "本地样本.pdf",
) =>
  page.locator("#pdf-file").setInputFiles({
    name,
    mimeType: "application/pdf",
    buffer: Buffer.from(await makeFixture(kind)),
  });

test("local preview, page navigation, rejection recovery and clear while offline", async ({
  page,
  context,
}) => {
  const requests: string[] = [];
  const errors: string[] = [];
  page.on("websocket", (socket) => requests.push(socket.url()));
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await context.setOffline(true);
  page.on("request", (req) => requests.push(req.url()));
  await upload(page);
  await expect(page.getByText("Page 1 of 2", { exact: true })).toBeVisible();
  await expect(page.locator("canvas")).toBeVisible();
  await page.getByText("Text on this page", { exact: true }).click();
  await expect(page.getByText(/PRIVATE_TEST_MARKER_20261006/)).toBeVisible();
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("Page 2 of 2", { exact: true })).toBeVisible();
  await upload(page, "form", "<script>private.pdf");
  await expect(page.getByRole("alert")).toContainText("form");
  await expect(page.getByText("Page 2 of 2", { exact: true })).toBeVisible();
  await page.screenshot({
    path: "docs/evidence/preview-desktop.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Clear session" }).click();
  await expect(page.locator("canvas")).toHaveCount(0);
  const storage = await page.evaluate(async () => ({
    local: localStorage.length,
    session: sessionStorage.length,
    indexed: (await indexedDB.databases()).length,
    caches: (await caches.keys()).length,
    sw: (await navigator.serviceWorker.getRegistrations()).length,
  }));
  expect(storage).toEqual({
    local: 0,
    session: 0,
    indexed: 0,
    caches: 0,
    sw: 0,
  });
  // Blob URLs are in-memory worker scripts, not network traffic.
  expect(requests.filter((url) => !url.startsWith("blob:"))).toEqual([]);
  expect(errors).toEqual([]);
});

test("resource failure disables input and retry recovers", async ({ page }) => {
  await page.route("**/pdf-resources.json", (route) => route.abort());
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Retry loading" }),
  ).toBeVisible();
  await expect(page.locator("#pdf-file")).toBeDisabled();
  await page.unroute("**/pdf-resources.json");
  await page.getByRole("button", { name: "Retry loading" }).click();
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await upload(page);
  await expect(page.locator("canvas")).toBeVisible();
});

test("cancel prevents a late first preview", async ({ page }) => {
  // Delay File reading to deterministically exercise cancellation before parsing.
  await page.addInitScript(() => {
    const read = FileReader.prototype.readAsArrayBuffer;
    const abort = FileReader.prototype.abort;
    const cancelled = new WeakSet<FileReader>();
    FileReader.prototype.readAsArrayBuffer = function (blob) {
      setTimeout(() => {
        if (!cancelled.has(this)) read.call(this, blob);
      }, 1000);
    };
    FileReader.prototype.abort = function () {
      cancelled.add(this);
      abort.call(this);
    };
  });
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await upload(page);
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Cancelled");
  await page.waitForTimeout(1200);
  await expect(page.locator("canvas")).toHaveCount(0);
  await expect(page.locator("#pdf-file")).toBeEnabled();
});

test("ten cycles release document workers and leave no storage", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const NativeWorker = window.Worker;
    const active = new Set<Worker>();
    Object.defineProperty(window, "__activeWorkers", {
      get: () => active.size,
    });
    window.Worker = class extends NativeWorker {
      constructor(url: string | URL, options?: WorkerOptions) {
        super(url, options);
        active.add(this);
      }
      terminate() {
        active.delete(this);
        super.terminate();
      }
    };
  });
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  for (let i = 0; i < 10; i++) {
    await upload(page);
    await expect(page.locator("canvas")).toBeVisible();
    await page.getByRole("button", { name: "Clear session" }).click();
    await expect
      .poll(() => page.evaluate(() => Reflect.get(window, "__activeWorkers")))
      .toBe(0);
  }
});

for (const width of [360, 768, 1280, 1920]) {
  test(`layout fits ${width}px and renders rotated crop`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    await expect(page.getByText("Ready for local processing")).toBeVisible();
    await upload(page, "geometry");
    await expect(page.locator("canvas")).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    if (width === 360)
      await page.screenshot({
        path: "docs/evidence/preview-mobile-width.png",
        fullPage: true,
      });
  });
}

test("synthetic 10-page load baseline after two warm-ups", async ({
  page,
  browser,
}) => {
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  const times: number[] = [];
  for (let i = 0; i < 22; i++) {
    const start = performance.now();
    await page
      .locator("#pdf-file")
      .setInputFiles("tests/fixtures/benchmark-10p-5mib.pdf");
    await expect(page.getByText("Page 1 of 10", { exact: true })).toBeVisible();
    if (i >= 2) times.push(performance.now() - start);
    await page.getByRole("button", { name: "Clear session" }).click();
  }
  const ordered = [...times].sort((a, b) => a - b);
  await writeFile(
    "docs/evidence/import-baseline.json",
    JSON.stringify(
      {
        date: "2026-10-06",
        browser: browser.version(),
        environment: "Windows desktop automation, not mobile",
        fixture: "benchmark-10p-5mib.pdf",
        warmups: 2,
        samples: times,
        p95Ms: ordered[18],
        notes:
          "End-to-end automation timing includes file selection. Synthetic unreferenced padding is not representative compressed image complexity.",
      },
      null,
      2,
    ),
  );
});

test("raster-only PDF renders offline with no unexpected network", async ({
  page,
  context,
}) => {
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await context.setOffline(true);
  const requests: string[] = [];
  page.on("request", (request) => {
    if (!request.url().startsWith("blob:")) requests.push(request.url());
  });
  await page.locator("#pdf-file").setInputFiles("tests/fixtures/scan.pdf");
  await expect(page.locator("canvas")).toBeVisible();
  await expect(page.getByText("Page 1 of 1", { exact: true })).toBeVisible();
  expect(requests).toEqual([]);
});

test("probe worker failure preserves the previous preview", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const original = Worker.prototype.postMessage;
    Worker.prototype.postMessage = function (
      data: unknown,
      options?: StructuredSerializeOptions | Transferable[],
    ) {
      if (
        Reflect.get(window, "__crashProbe") &&
        typeof data === "object" &&
        data !== null &&
        "bytes" in data
      ) {
        queueMicrotask(() =>
          this.dispatchEvent(
            new ErrorEvent("error", {
              message: "synthetic worker failure",
              cancelable: true,
            }),
          ),
        );
        return;
      }
      original.call(
        this,
        data,
        Array.isArray(options) ? { transfer: options } : options,
      );
    };
  });
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await upload(page);
  await expect(page.getByText("Page 1 of 2", { exact: true })).toBeVisible();
  await page.evaluate(() => Reflect.set(window, "__crashProbe", true));
  await upload(page);
  await expect(page.getByRole("alert")).toContainText("couldn’t preview");
  await expect(page.getByText("Page 1 of 2", { exact: true })).toBeVisible();
  await expect(page.locator("canvas")).toBeVisible();
});

test("deadline aborts file reading without replacing the previous preview", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const timer = window.setTimeout;
    window.setTimeout = ((
      handler: TimerHandler,
      timeout?: number,
      ...args: unknown[]
    ) =>
      timer(
        handler,
        timeout === 120000 && Reflect.get(window, "__shortDeadline")
          ? 30
          : timeout,
        ...args,
      )) as typeof window.setTimeout;
    const read = FileReader.prototype.readAsArrayBuffer;
    const abort = FileReader.prototype.abort;
    const stopped = new WeakSet<FileReader>();
    FileReader.prototype.abort = function () {
      stopped.add(this);
      abort.call(this);
    };
    FileReader.prototype.readAsArrayBuffer = function (blob) {
      if (!Reflect.get(window, "__shortDeadline")) {
        read.call(this, blob);
        return;
      }
      timer(() => {
        if (!stopped.has(this)) read.call(this, blob);
      }, 300);
    };
  });
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await upload(page);
  await expect(page.locator("canvas")).toBeVisible();
  await page.evaluate(() => Reflect.set(window, "__shortDeadline", true));
  await upload(page);
  await expect(page.getByRole("alert")).toContainText("too long");
  await expect(page.getByText("Page 1 of 2", { exact: true })).toBeVisible();
  await expect(page.locator("#pdf-file")).toBeEnabled();
});
