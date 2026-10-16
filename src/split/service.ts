import SplitWorker from "./split.worker?worker&inline";
import { readLocalFile } from "../platform/abort";
export async function processSplit(
  file: File,
  groups: number[][],
  adjust: boolean,
  budget: number,
  signal: AbortSignal,
  progress: (done: number) => void,
): Promise<Uint8Array[]> {
  const bytes = await readLocalFile(file, signal);
  if (signal.aborted) throw new Error("Cancelled");
  return new Promise((resolve, reject) => {
    const worker = new SplitWorker();
    const clean = () => {
      signal.removeEventListener("abort", abort);
      worker.onmessage = null;
      worker.onerror = null;
      worker.terminate();
    };
    const abort = () => {
      clean();
      reject(
        new Error("Cancelled. Your source and previous results are unchanged."),
      );
    };
    signal.addEventListener("abort", abort, { once: true });
    worker.onerror = (e) => {
      e.preventDefault();
      clean();
      reject(
        new Error(
          "Splitting failed. Your source and previous results are unchanged.",
        ),
      );
    };
    worker.onmessage = (e) => {
      if (e.data.error) {
        clean();
        reject(new Error(e.data.error));
      } else if (e.data.outputs) {
        clean();
        resolve(e.data.outputs);
      } else if (e.data.done) progress(e.data.done);
    };
    if (signal.aborted) abort();
    else
      try {
        worker.postMessage({ bytes, groups, adjust, budget }, [bytes.buffer]);
      } catch {
        abort();
      }
  });
}
