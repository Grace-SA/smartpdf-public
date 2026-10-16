import PhotoWorker from "./photos.worker?worker&inline";
import type { PhotoInput } from "./generate";
import { readLocalFile } from "../platform/abort";
import { inspectImage, photoCopy, type PhotoSettings } from "./model";
export function preparePhotos(signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const worker = new PhotoWorker();
    const clean = () => {
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
      worker.terminate();
    };
    const abort = () => {
      clean();
      reject(new Error("Cancelled"));
    };
    const timer = setTimeout(abort, 15000);
    signal.addEventListener("abort", abort, { once: true });
    worker.onmessage = (e) => {
      if (e.data.ready) {
        clean();
        resolve();
      }
    };
    worker.onerror = (e) => {
      e.preventDefault();
      abort();
    };
    if (signal.aborted) abort();
  });
}
export async function createPhotos(
  items: { file: File; turns: number }[],
  settings: PhotoSettings,
  signal: AbortSignal,
  stage: (s: string) => void,
): Promise<Uint8Array> {
  const inputs: PhotoInput[] = [];
  for (const [i, item] of items.entries()) {
    stage(`Reading image ${i + 1} of ${items.length}…`);
    const bytes = await readLocalFile(item.file, signal);
    inspectImage(bytes);
    inputs.push({ bytes, turns: item.turns });
  }
  if (signal.aborted) throw new Error("Cancelled");
  return new Promise((resolve, reject) => {
    const worker = new PhotoWorker();
    const clean = () => {
      signal.removeEventListener("abort", abort);
      worker.onmessage = null;
      worker.onerror = null;
      worker.terminate();
    };
    const abort = () => {
      clean();
      reject(new Error("Cancelled"));
    };
    signal.addEventListener("abort", abort, { once: true });
    worker.onerror = (e) => {
      e.preventDefault();
      clean();
      reject(new Error(photoCopy.failed));
    };
    worker.onmessage = (e) => {
      if (e.data.done)
        stage(`Creating page ${e.data.done} of ${items.length}…`);
      if (e.data.bytes) {
        clean();
        resolve(e.data.bytes);
      }
      if (e.data.failed) {
        clean();
        reject(new Error(photoCopy.failed));
      }
    };
    if (signal.aborted) {
      abort();
      return;
    }
    try {
      worker.postMessage(
        { inputs, settings },
        inputs.map((x) => x.bytes.buffer as ArrayBuffer),
      );
    } catch {
      clean();
      reject(new Error(photoCopy.failed));
    }
  });
}
