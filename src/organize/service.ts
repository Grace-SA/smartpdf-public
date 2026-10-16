import Worker from "./organize.worker?worker&inline";
import { readLocalFile } from "../platform/abort";
import type { CombineInspection } from "../combine/generate";
import type { PageEntry } from "./model";
const messages = [
  "Choose at least one page, without duplicates, and rotate in 90-degree steps.",
  "This PDF cannot be organized while preserving its supported structure. Your previous document is unchanged.",
  "A retained link, bookmark, tag, form or document setting still refers to a deleted page. Keep that page or cancel these changes; no structure has been silently removed.",
  "The organized PDF did not pass validation. Your previous document is unchanged.",
];
async function requestPages(
  file: File,
  plan: PageEntry[],
  signal: AbortSignal,
  adjustDeletedAssociations = false,
  operation?: "inspect",
): Promise<Uint8Array | CombineInspection> {
  const bytes = await readLocalFile(file, signal);
  if (signal.aborted) throw new Error("Cancelled");
  return new Promise((resolve, reject) => {
    const worker = new Worker();
    const clean = () => {
      signal.removeEventListener("abort", abort);
      worker.onmessage = null;
      worker.onerror = null;
      worker.terminate();
    };
    const abort = () => {
      clean();
      reject(new Error("Cancelled. Your previous document is unchanged."));
    };
    signal.addEventListener("abort", abort, { once: true });
    worker.onerror = (e) => {
      e.preventDefault();
      clean();
      reject(new Error(messages[3]));
    };
    worker.onmessage = (e) => {
      if (e.data.result && operation === "inspect") {
        clean();
        resolve(e.data.result);
      } else if (e.data.failed) {
        clean();
        reject(
          new Error(
            Number.isInteger(e.data.code)
              ? (messages[e.data.code] ?? messages[3])
              : messages[3],
          ),
        );
      } else if (e.data.bytes) {
        clean();
        resolve(e.data.bytes);
      }
    };
    if (signal.aborted) {
      abort();
      return;
    }
    try {
      worker.postMessage(
        { bytes, plan, adjustDeletedAssociations, operation },
        [bytes.buffer],
      );
    } catch {
      clean();
      reject(new Error(messages[3]));
    }
  });
}

export async function inspectPages(file: File, signal: AbortSignal) {
  return (await requestPages(
    file,
    [],
    signal,
    false,
    "inspect",
  )) as CombineInspection;
}
export async function processPages(
  file: File,
  plan: PageEntry[],
  signal: AbortSignal,
  adjustDeletedAssociations = false,
) {
  return (await requestPages(
    file,
    plan,
    signal,
    adjustDeletedAssociations,
  )) as Uint8Array;
}
