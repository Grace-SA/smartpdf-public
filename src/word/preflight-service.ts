import CheckWorker from "./preflight.worker?worker";
import type { WordCheck } from "./preflight-core";
export function checkWordLocally(
  file: File,
  signal: AbortSignal,
): Promise<WordCheck> {
  return new Promise((resolve, reject) => {
    const worker = new CheckWorker();
    const finish = () => {
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
      worker.terminate();
    };
    const abort = () => {
      finish();
      reject(new DOMException("Cancelled", "AbortError"));
    };
    const timer = setTimeout(() => {
      finish();
      reject(
        Error(
          "Local checking took too long. Simplify the document or save a new DOCX copy in Word.",
        ),
      );
    }, 15000);
    signal.addEventListener("abort", abort, { once: true });
    worker.onmessage = (event) => {
      finish();
      if (event.data.result) resolve(event.data.result);
      else reject(Error(event.data.error));
    };
    worker.onerror = (event) => {
      event.preventDefault();
      finish();
      reject(
        Error(
          "Local document checking is unavailable. Reload this page and try again.",
        ),
      );
    };
    if (signal.aborted) {
      abort();
      return;
    }
    worker.postMessage(file);
  });
}
