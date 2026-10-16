import { expect, test } from "@playwright/test";

test("probe waits for worker readiness before sending document bytes", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const NativeWorker = window.Worker;
    const ready = new WeakSet<Worker>();
    const send = NativeWorker.prototype.postMessage;
    NativeWorker.prototype.postMessage = function (
      message: unknown,
      transferOrOptions?: Transferable[] | StructuredSerializeOptions,
    ) {
      const data = message as { id?: unknown; bytes?: unknown } | null;
      if (
        data &&
        typeof data.id === "number" &&
        data.bytes instanceof Uint8Array &&
        !ready.has(this)
      )
        throw new Error("Probe command was sent before worker readiness");
      return send.call(
        this,
        message,
        Array.isArray(transferOrOptions)
          ? { transfer: transferOrOptions }
          : transferOrOptions,
      );
    };
    window.Worker = class extends NativeWorker {
      constructor(url: string | URL, options?: WorkerOptions) {
        super(url, options);
        this.addEventListener("message", (event) => {
          if (event.data?.ready === true) ready.add(this);
        });
      }
    };
  });
  await page.goto("/sign-pdf/");
  await page
    .locator("#pdf-file")
    .setInputFiles("tests/fixtures/m5/normal-a4.pdf");
  await expect(
    page.getByRole("button", { name: "Add signature", exact: true }),
  ).toBeEnabled();
  await expect(
    page.locator('.sign-sheet[data-current="true"] canvas'),
  ).toHaveCount(1);
});

test("renderer waits for PDF.js readiness before sending resource data", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const NativeWorker = window.Worker;
    const ready = new WeakSet<Worker>();
    const send = NativeWorker.prototype.postMessage;
    NativeWorker.prototype.postMessage = function (
      data: unknown,
      options?: Transferable[] | StructuredSerializeOptions,
    ) {
      if (
        data &&
        typeof data === "object" &&
        "smartPdfResources" in data &&
        !ready.has(this)
      )
        throw new Error(
          "Renderer resources sent before PDF.js worker readiness",
        );
      return Reflect.apply(send, this, [data, options]);
    };
    window.Worker = class extends NativeWorker {
      constructor(url: string | URL, options?: WorkerOptions) {
        super(url, options);
        this.addEventListener("message", ({ data }) => {
          if (
            data?.sourceName === "worker" &&
            data?.targetName === "main" &&
            data?.action === "ready"
          )
            ready.add(this);
        });
      }
    };
  });
  await page.goto("/sign-pdf/");
  await page
    .locator("#pdf-file")
    .setInputFiles("tests/fixtures/m5/normal-a4.pdf");
  await expect(
    page.getByRole("button", { name: "Add signature", exact: true }),
  ).toBeEnabled();
});
