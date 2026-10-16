import type { Page } from "@playwright/test";

// Synthetic browser tests only: record lifecycle categories, never payloads.
export async function workerDiagnostics(page: Page) {
  await page.addInitScript(() => {
    const events: string[] = [];
    Reflect.set(window, "syntheticWorkerEvents", events);
    const record = (value: string) => {
      events.push(`${Math.round(performance.now())}:${value}`);
      if (events.length > 160) events.shift();
    };
    let sequence = 0;
    const ids = new WeakMap<Worker, number>();
    const NativeWorker = window.Worker;
    const send = NativeWorker.prototype.postMessage;
    const terminate = NativeWorker.prototype.terminate;
    NativeWorker.prototype.postMessage = function (
      data: unknown,
      transferOrOptions?: Transferable[] | StructuredSerializeOptions,
    ) {
      const message = data as { id?: unknown; bytes?: unknown } | null;
      if (
        typeof message?.id === "number" &&
        message?.bytes instanceof Uint8Array
      )
        record(
          `probe-send:${ids.get(this)}:${message.id}:${message.bytes.length}`,
        );
      return Reflect.apply(send, this, [data, transferOrOptions]);
    };
    NativeWorker.prototype.terminate = function () {
      record(`terminate:${ids.get(this)}`);
      return Reflect.apply(terminate, this, []);
    };
    window.Worker = class extends NativeWorker {
      constructor(url: string | URL, options?: WorkerOptions) {
        super(url, options);
        const id = ++sequence;
        ids.set(this, id);
        record(`create:${id}`);
        this.addEventListener("message", ({ data }) => {
          if (data?.ready === true) record(`probe-ready:${id}`);
          if (typeof data?.id === "number" && data?.result)
            record(`probe-result:${id}:${data.id}:${Boolean(data.result.ok)}`);
        });
        this.addEventListener("error", () => record(`error:${id}`));
        this.addEventListener("messageerror", () =>
          record(`messageerror:${id}`),
        );
      }
    };
  });
}

export async function reportWorkerDiagnostics(page: Page) {
  if (page.isClosed()) return;
  console.log(
    "SYNTHETIC_WORKER_EVENTS",
    await page.evaluate(() => Reflect.get(window, "syntheticWorkerEvents")),
  );
}
