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

test("resource warming starts no worker before a file is selected", async ({
  page,
}) => {
  await trackResources(page);
  await page.goto("/sign-pdf/");
  await expect(page.locator(".status.ready")).toBeAttached();
  await expect
    .poll(() => page.evaluate(() => Reflect.get(window, "__resources").workers))
    .toBe(0);
  await page.locator("#pdf-file").setInputFiles("tests/fixtures/plain.pdf");
  await expect(
    page.locator('.sign-sheet[data-current="true"] canvas'),
  ).toBeVisible();
  await page.getByText("← All tools", { exact: true }).click();
  await expect
    .poll(() => page.evaluate(() => Reflect.get(window, "__resources").workers))
    .toBe(0);
});

for (const failure of ["throw", "silent"] as const) {
  test(`renderer ${failure} rejects the document, releases workers and permits retry`, async ({
    page,
  }) => {
    await trackResources(page);
    await page.addInitScript((mode) => {
      const NativeWorker = window.Worker;
      window.Worker = class extends NativeWorker {
        constructor(url: string | URL, options?: WorkerOptions) {
          if (
            options?.type === "module" &&
            !Reflect.get(window, "__allowRenderer")
          ) {
            const broken = URL.createObjectURL(
              new Blob(
                [
                  mode === "throw"
                    ? 'throw new Error("SYNTHETIC_BOOT_FAILURE")'
                    : "/* no ready packet */",
                ],
                { type: "text/javascript" },
              ),
            );
            super(broken, options);
            URL.revokeObjectURL(broken);
          } else super(url, options);
        }
      };
    }, failure);
    await page.goto("/sign-pdf/");
    await expect(page.locator(".status.ready")).toBeAttached();
    await page.locator("#pdf-file").setInputFiles("tests/fixtures/plain.pdf");
    await expect(page.getByRole("alert")).toContainText("couldn’t preview", {
      timeout: 22000,
    });
    await expect(page.locator("canvas")).toHaveCount(0);
    await expect
      .poll(() =>
        page.evaluate(() => Reflect.get(window, "__resources").workers),
      )
      .toBe(0);
    await page.evaluate(() => Reflect.set(window, "__allowRenderer", true));
    await page.locator("#pdf-file").setInputFiles("tests/fixtures/plain.pdf");
    await expect(
      page.locator('.sign-sheet[data-current="true"] canvas'),
    ).toBeVisible();
    await page.getByText("← All tools", { exact: true }).click();
    await expect
      .poll(() =>
        page.evaluate(() => Reflect.get(window, "__resources").workers),
      )
      .toBe(0);
  });
}
