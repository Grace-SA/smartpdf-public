import CheckWorker from "./preflight.worker?worker";

export function checkPptLocally(
  file: File,
  signal: AbortSignal,
): Promise<void> {
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
        Error("Local checks took too long. Save a smaller PPTX in PowerPoint."),
      );
    }, 15000);
    signal.addEventListener("abort", abort, { once: true });
    worker.onmessage = (event) => {
      finish();
      if (event.data.result) resolve();
      else reject(Error(event.data.error));
    };
    worker.onerror = (event) => {
      event.preventDefault();
      finish();
      reject(Error("Local checks could not load. Reload and try again."));
    };
    if (signal.aborted) abort();
    else worker.postMessage(file);
  });
}
