import FontWorker from "./fonts.worker?worker&inline";
import { readLocalFile } from "../platform/abort";
export async function fontWarning(
  file: File,
  signal: AbortSignal,
): Promise<boolean> {
  const bytes = await readLocalFile(file, signal);
  if (signal.aborted) return false;
  return new Promise((resolve) => {
    const worker = new FontWorker();
    const clean = () => {
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
      worker.terminate();
    };
    const abort = () => {
      clean();
      resolve(false);
    };
    const timer = setTimeout(() => {
      clean();
      resolve(true);
    }, 15000);
    signal.addEventListener("abort", abort, { once: true });
    worker.onmessage = (event: MessageEvent<{ warning: boolean }>) => {
      clean();
      resolve(event.data.warning);
    };
    worker.onerror = (event) => {
      event.preventDefault();
      clean();
      resolve(true);
    };
    if (signal.aborted) abort();
    else
      try {
        worker.postMessage(bytes, [bytes.buffer]);
      } catch {
        clean();
        resolve(true);
      }
  });
}
