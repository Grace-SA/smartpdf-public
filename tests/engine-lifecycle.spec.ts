import { test, expect, type Page } from "@playwright/test";

async function trackResources(page: Page) {
  await page.addInitScript(() => {
    const NativeWorker = Worker;
    const workers = new Set<Worker>();
    const urls = new Set<string>();
    const create = URL.createObjectURL;
    const revoke = URL.revokeObjectURL;
    URL.createObjectURL = (blob) => {
      const url = create(blob);
      // Vite inline probe URLs revoke themselves inside the worker realm.
      // Track the renderer URL owned and revoked by Engine in this realm.
      if ("type" in blob && blob.type === "text/javascript") urls.add(url);
      return url;
    };
    URL.revokeObjectURL = (url) => {
      urls.delete(url);
      revoke(url);
    };
    Object.defineProperty(window, "__resources", {
      get: () => ({ workers: workers.size, urls: urls.size }),
    });
    window.Worker = class extends NativeWorker {
      constructor(url: string | URL, options?: WorkerOptions) {
        super(url, options);
        workers.add(this);
      }
      terminate() {
        workers.delete(this);
        super.terminate();
      }
      postMessage(
        data: unknown,
        options?: StructuredSerializeOptions | Transferable[],
      ) {
        if (
          Reflect.get(window, "__throwTransfer") &&
          data &&
          typeof data === "object" &&
          "bytes" in data
        )
          throw new DOMException(
            "Synthetic transfer failure",
            "DataCloneError",
          );
        super.postMessage(
          data,
          Array.isArray(options) ? { transfer: options } : options,
        );
      }
    };
  });
}

for (const failure of ["throw", "silent"] as const) {
  test(`renderer ${failure} prevents false ready, releases resources and permits retry`, async ({
    page,
  }) => {
    await trackResources(page);
    await page.route("**/assets/pdf.worker.min-*.mjs", (route) =>
      route.fulfill({
        contentType: "text/javascript",
        body:
          failure === "throw"
            ? 'throw new Error("SYNTHETIC_BOOT_FAILURE")'
            : "/* no ready packet */",
      }),
    );
    await page.goto("/");
    await expect(
      page.getByRole("button", { name: "Retry loading" }),
    ).toBeVisible({ timeout: 22000 });
    await expect(page.getByText("Ready for local processing")).toHaveCount(0);
    await expect(page.locator("#pdf-file")).toBeDisabled();
    await expect
      .poll(() => page.evaluate(() => Reflect.get(window, "__resources")))
      .toEqual({ workers: 0, urls: 0 });
    await page.unroute("**/assets/pdf.worker.min-*.mjs");
    await page.getByRole("button", { name: "Retry loading" }).click();
    await expect(page.getByText("Ready for local processing")).toBeVisible();
    await page.locator("#pdf-file").setInputFiles("tests/fixtures/plain.pdf");
    await expect(page.getByText("Page 1 of 2", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Clear session" }).click();
    await expect
      .poll(() =>
        page.evaluate(() => Reflect.get(window, "__resources").workers),
      )
      .toBe(0);
  });
}

test("synchronous probe transfer failure keeps old page, releases worker and recovers", async ({
  page,
}) => {
  await trackResources(page);
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await page.locator("#pdf-file").setInputFiles("tests/fixtures/plain.pdf");
  await expect(page.locator("canvas")).toBeVisible();
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("Page 2 of 2", { exact: true })).toBeVisible();
  await page.evaluate(() => Reflect.set(window, "__throwTransfer", true));
  await page.locator("#pdf-file").setInputFiles("tests/fixtures/plain.pdf");
  await expect(page.getByRole("alert")).toContainText("couldn’t preview");
  await expect(page.getByText("Page 2 of 2", { exact: true })).toBeVisible();
  await expect(page.locator("canvas")).toBeVisible();
  await expect
    .poll(() => page.evaluate(() => Reflect.get(window, "__resources").workers))
    .toBe(1);
  await page.getByRole("button", { name: "Clear session" }).click();
  await expect
    .poll(() => page.evaluate(() => Reflect.get(window, "__resources").workers))
    .toBe(0);
  await page.evaluate(() => Reflect.set(window, "__throwTransfer", false));
  await page.locator("#pdf-file").setInputFiles("tests/fixtures/plain.pdf");
  await expect(page.getByText("Page 1 of 2", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Clear session" }).click();
  await expect
    .poll(() => page.evaluate(() => Reflect.get(window, "__resources").workers))
    .toBe(0);
});
