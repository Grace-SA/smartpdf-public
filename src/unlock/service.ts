import { qpdfPreparation } from "../platform/qpdf-preparation";
import UnlockWorker from "./unlock.worker?worker&inline";
import { LIMITS } from "../core/contracts";
import { UnlockFailure, unlockMessages } from "./model";
import type { UnlockRequest, UnlockResult } from "./engine";
type Reply =
  | { kind: "stage"; stage: "unlock" | "verify" }
  | { kind: "result"; ok: true; result: UnlockResult }
  | { kind: "result"; ok: false; reason: keyof typeof unlockMessages };
export const prepareUnlock = qpdfPreparation(
  (reason) => new UnlockFailure(reason),
);
function waitFor<T>(
  promise: Promise<T>,
  signal: AbortSignal,
  remaining: number,
): Promise<T> {
  if (signal.aborted) return Promise.reject(new UnlockFailure("cancelled"));
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
    };
    const abort = () => {
      cleanup();
      reject(new UnlockFailure("cancelled"));
    };
    const timer = setTimeout(
      () => {
        cleanup();
        reject(new UnlockFailure("timeout"));
      },
      Math.max(1, remaining),
    );
    signal.addEventListener("abort", abort, { once: true });
    promise.then(
      (value) => {
        cleanup();
        resolve(value);
      },
      (error) => {
        cleanup();
        reject(error);
      },
    );
  });
}
export async function unlockOperation(
  file: File,
  operation:
    | { kind: "inspect" }
    | { kind: "unlock"; password: string; ordinary: boolean },
  signal: AbortSignal,
  stage: (value: "unlock" | "verify") => void = () => {},
): Promise<UnlockResult> {
  if (signal.aborted) throw new UnlockFailure("cancelled");
  if (file.size < 1) throw new UnlockFailure("invalid");
  if (file.size > LIMITS.bytes) throw new UnlockFailure("resource");
  const started = Date.now();
  let wasm: Uint8Array<ArrayBuffer>, bytes: ArrayBuffer;
  try {
    wasm = await waitFor(prepareUnlock(signal), signal, LIMITS.timeoutMs);
    bytes = await waitFor(
      file.arrayBuffer(),
      signal,
      LIMITS.timeoutMs - (Date.now() - started),
    );
  } catch (error) {
    throw error instanceof UnlockFailure ? error : new UnlockFailure("engine");
  }
  if (signal.aborted) throw new UnlockFailure("cancelled");
  const request = { ...operation, bytes } as UnlockRequest;
  return await new Promise<UnlockResult>((resolve, reject) => {
    let worker: Worker;
    try {
      worker = new UnlockWorker();
    } catch {
      reject(new UnlockFailure("engine"));
      return;
    }
    const cleanup = () => {
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
      worker.onmessage = null;
      worker.onerror = null;
      worker.terminate();
    };
    const fail = (reason: keyof typeof unlockMessages) => {
      cleanup();
      reject(new UnlockFailure(reason));
    };
    const abort = () => fail("cancelled");
    const timer = setTimeout(
      () => fail("timeout"),
      Math.max(1, LIMITS.timeoutMs - (Date.now() - started)),
    );
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) {
      abort();
      return;
    }
    worker.onerror = () => fail("engine");
    worker.onmessage = (event: MessageEvent<Reply>) => {
      const message = event.data;
      if (message.kind === "stage") {
        if (message.stage === "unlock" || message.stage === "verify")
          stage(message.stage);
        return;
      }
      if (message.kind !== "result") {
        fail("engine");
        return;
      }
      if (!message.ok) {
        fail(
          Object.hasOwn(unlockMessages, message.reason)
            ? message.reason
            : "engine",
        );
        return;
      }
      const result = message.result;
      if (
        "bytes" in result
          ? !(result.bytes instanceof ArrayBuffer) ||
            !Number.isInteger(result.pages) ||
            result.pages < 1 ||
            result.pages > LIMITS.pages ||
            result.bytes.byteLength > LIMITS.bytes
          : !["password-required", "accessible", "not-encrypted"].includes(
              result.status,
            )
      ) {
        fail("validation");
        return;
      }
      cleanup();
      resolve(result);
    };
    try {
      const copy = wasm.slice().buffer;
      worker.postMessage({ request, wasm: copy }, [bytes, copy]);
    } catch {
      fail("engine");
    } finally {
      if (request.kind === "unlock") request.password = "";
      if (operation.kind === "unlock") operation.password = "";
    }
  });
}
