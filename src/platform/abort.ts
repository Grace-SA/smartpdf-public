import { ProbeFailure } from "../core/contracts";

export function untilAborted<T>(
  promise: Promise<T>,
  signal: AbortSignal,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const abort = () => reject(new ProbeFailure("CANCELLED"));
    if (signal.aborted) {
      void promise.catch(() => undefined);
      abort();
      return;
    }
    signal.addEventListener("abort", abort, { once: true });
    promise
      .then(resolve, reject)
      .finally(() => signal.removeEventListener("abort", abort));
  });
}

export function readLocalFile(
  file: Blob,
  signal: AbortSignal,
): Promise<Uint8Array> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    const abort = () => {
      reader.abort();
      finish();
      reject(new ProbeFailure("CANCELLED"));
    };
    const finish = () => {
      signal.removeEventListener("abort", abort);
      reader.onload = null;
      reader.onerror = null;
      reader.onabort = null;
    };
    if (signal.aborted) {
      abort();
      return;
    }
    signal.addEventListener("abort", abort, { once: true });
    reader.onload = () => {
      const value = reader.result;
      finish();
      // FileReader's ArrayBuffer can originate in another realm (for example
      // an embedded preview on WebKit). instanceof rejects valid foreign
      // buffers; the DOM contract gives only string | ArrayBuffer | null.
      if (value !== null && typeof value !== "string")
        resolve(new Uint8Array(value));
      else reject(new ProbeFailure("INVALID_INPUT"));
    };
    reader.onerror = () => {
      finish();
      reject(new ProbeFailure("INVALID_INPUT"));
    };
    reader.readAsArrayBuffer(file);
  });
}
