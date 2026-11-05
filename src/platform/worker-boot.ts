import { ProbeFailure } from "../core/contracts";

export function waitForBoot(
  port: Worker,
  ready: (data: Record<string, unknown> | null) => boolean,
  signal?: AbortSignal,
  start?: () => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const clean = () => {
      clearTimeout(timer);
      port.removeEventListener("message", message);
      port.removeEventListener("error", error);
      signal?.removeEventListener("abort", abort);
    };
    const fail = (reason: Error) => {
      // A cancelled blob worker can report a queued load error after its boot
      // listeners are removed (notably in WebKit). Stop it synchronously and
      // consume only that failed worker's late errors, not live worker errors.
      port.addEventListener("error", (event) => event.preventDefault());
      port.terminate();
      clean();
      reject(reason);
    };
    const message = (event: MessageEvent) => {
      if (ready(event.data)) {
        clean();
        resolve();
      }
    };
    const error = (event: ErrorEvent) => {
      event.preventDefault();
      fail(new Error("RESOURCE_LOAD_FAILED"));
    };
    const abort = () => fail(new ProbeFailure("CANCELLED"));
    const timer = setTimeout(
      () => fail(new Error("RESOURCE_LOAD_FAILED")),
      15000,
    );
    port.addEventListener("message", message);
    port.addEventListener("error", error);
    signal?.addEventListener("abort", abort, { once: true });
    if (signal?.aborted) abort();
    else {
      try {
        start?.();
      } catch (reason) {
        fail(
          reason instanceof Error ? reason : new Error("RESOURCE_LOAD_FAILED"),
        );
      }
    }
  });
}
