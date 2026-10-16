import type { CompressionLevel } from "./model";
import CompressionWorker from "./compress.worker?worker";

type PreparedReply = { kind: "prepared"; ok: boolean; message?: string };
type CompressedReply =
  | { kind: "compressed"; id: number; ok: true; bytes: ArrayBuffer }
  | { kind: "compressed"; id: number; ok: false; message: string };

let worker: Worker | null = null;
let preparation: Promise<void> | null = null;
let requestId = 0;

function resetWorker() {
  worker?.terminate();
  worker = null;
  preparation = null;
}

/** Release the persistent WASM worker when the application instance stops. */
export function disposeCompress() {
  resetWorker();
}

export function prepareCompress(signal: AbortSignal): Promise<void> {
  if (signal.aborted)
    return Promise.reject(new DOMException("Aborted", "AbortError"));
  if (preparation) return preparation;
  const localWorker = new CompressionWorker();
  worker = localWorker;
  preparation = new Promise<void>((resolve, reject) => {
    const clean = () => {
      signal.removeEventListener("abort", abort);
      localWorker.onmessage = null;
      localWorker.onerror = null;
    };
    const abort = () => {
      clean();
      resetWorker();
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal.addEventListener("abort", abort, { once: true });
    localWorker.onerror = () => {
      clean();
      resetWorker();
      reject(new Error("The local compression engine stopped unexpectedly."));
    };
    localWorker.onmessage = (event: MessageEvent<PreparedReply>) => {
      if (event.data.kind !== "prepared") return;
      clean();
      if (event.data.ok) resolve();
      else {
        const message =
          event.data.message ?? "The local compression engine could not load.";
        resetWorker();
        reject(new Error(message));
      }
    };
    localWorker.postMessage({
      kind: "prepare",
      wasmUrl: new URL("/qpdf.wasm", window.location.origin).href,
    });
  });
  return preparation;
}

export async function compressPdf(
  file: File,
  level: CompressionLevel,
  signal: AbortSignal,
  stage: (value: string) => void,
): Promise<Uint8Array> {
  stage("Loading the local compression engine…");
  await prepareCompress(signal);
  const localWorker = worker;
  if (!localWorker)
    throw new Error("The local compression engine is not ready.");
  const source = await file.arrayBuffer();
  if (signal.aborted) throw new DOMException("Aborted", "AbortError");
  stage("Compressing locally…");
  const id = ++requestId;
  return await new Promise<Uint8Array>((resolve, reject) => {
    const clean = () => {
      signal.removeEventListener("abort", abort);
      localWorker.onmessage = null;
      localWorker.onerror = null;
    };
    const abort = () => {
      clean();
      resetWorker();
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal.addEventListener("abort", abort, { once: true });
    localWorker.onerror = () => {
      clean();
      resetWorker();
      reject(new Error("The local compression engine stopped unexpectedly."));
    };
    localWorker.onmessage = (event: MessageEvent<CompressedReply>) => {
      if (event.data.kind !== "compressed" || event.data.id !== id) return;
      clean();
      if (event.data.ok) resolve(new Uint8Array(event.data.bytes));
      else {
        // A failed qpdf call may leave the persistent virtual filesystem or
        // WASM runtime in an unknown state. Start clean on the next attempt.
        resetWorker();
        reject(new Error(event.data.message));
      }
    };
    localWorker.postMessage({ kind: "compress", id, bytes: source, level }, [
      source,
    ]);
  });
}
