/// <reference lib="webworker" />
import { processUnlock, type UnlockRequest } from "./engine";
import { UnlockFailure } from "./model";
import { limitWasmHeap } from "./memory";

// This private, one-shot worker must not expose parser diagnostics or content.
console.log = console.warn = console.error = () => {};
let started = false;
self.onmessage = async (
  event: MessageEvent<{ request: UnlockRequest; wasm: ArrayBuffer }>,
) => {
  if (started) return;
  started = true;
  const { request, wasm } = event.data;
  const memory = limitWasmHeap();
  const url = new URL("/qpdf.wasm", self.location.origin).href;
  // This pinned wrapper does not accept wasmBinary. Serve only the transferred
  // public engine bytes through its fetch adapter; no network or CSP exception.
  self.fetch = (input: RequestInfo | URL) => {
    const requested =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.href
          : input.url;
    return requested === url
      ? Promise.resolve(
          new Response(wasm, {
            headers: { "content-type": "application/wasm" },
          }),
        )
      : Promise.reject(new UnlockFailure("engine"));
  };
  try {
    const result = await processUnlock(request, url, (stage) =>
      self.postMessage({ kind: "stage", stage }),
    );
    if ("bytes" in result)
      self.postMessage({ kind: "result", ok: true, result }, [result.bytes]);
    else self.postMessage({ kind: "result", ok: true, result });
  } catch (error) {
    self.postMessage({
      kind: "result",
      ok: false,
      reason: memory.exhausted()
        ? "resource"
        : error instanceof UnlockFailure
          ? error.reason
          : "engine",
    });
  } finally {
    if (request.kind === "unlock") request.password = "";
    memory.restore();
  }
};
