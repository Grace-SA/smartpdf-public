import CombineWorker from "./combine.worker?worker&inline";
import { readLocalFile } from "../platform/abort";
import type { CombineInspection } from "./generate";
import { publicFailureMessage } from "./failure-messages";

export function prepareCombine(signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const worker = new CombineWorker();
    const clean = () => {
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
      worker.terminate();
    };
    const abort = () => {
      clean();
      reject(new Error("Combine resources could not load."));
    };
    const timer = setTimeout(abort, 15000);
    signal.addEventListener("abort", abort, { once: true });
    worker.onerror = (event) => {
      event.preventDefault();
      abort();
    };
    worker.onmessage = (event) => {
      if (event.data.ready) {
        clean();
        resolve();
      }
    };
    if (signal.aborted) abort();
  });
}
export async function processPdfs(
  operation: "inspect" | "combine",
  files: File[],
  signal: AbortSignal,
  stage: (text: string) => void,
): Promise<{ result?: CombineInspection; bytes?: Uint8Array }> {
  const inputs: Uint8Array[] = [];
  for (const [index, file] of files.entries()) {
    stage(`Reading PDF ${index + 1} of ${files.length}…`);
    inputs.push(await readLocalFile(file, signal));
  }
  if (signal.aborted) throw new Error("Cancelled");
  return new Promise((resolve, reject) => {
    const worker = new CombineWorker();
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
    worker.onerror = (event) => {
      event.preventDefault();
      clean();
      reject(
        new Error("The PDF task failed. Your previous document is unchanged."),
      );
    };
    worker.onmessage = (event) => {
      if (typeof event.data.stage === "string") stage(event.data.stage);
      if (event.data.done)
        stage(`Combined PDF ${event.data.done} of ${files.length}…`);
      if (event.data.failed) {
        clean();
        reject(
          new Error(
            publicFailureMessage(event.data.failureCode) ??
              "The PDF task failed validation. Try fewer or simpler PDFs. Your previous document is unchanged.",
          ),
        );
      }
      if (event.data.result || event.data.bytes) {
        clean();
        resolve(event.data);
      }
    };
    if (signal.aborted) {
      abort();
      return;
    }
    stage(
      operation === "inspect"
        ? "Checking PDF structure…"
        : "Checking and combining PDFs…",
    );
    try {
      worker.postMessage(
        { operation, inputs },
        inputs.map((b) => b.buffer as ArrayBuffer),
      );
    } catch {
      clean();
      reject(
        new Error(
          "The PDF task could not start. Your previous document is unchanged.",
        ),
      );
    }
  });
}
