import type { Sheet } from "./workbook";
export async function inspectWorkbook(
  file: File,
  signal: AbortSignal,
): Promise<Sheet[]> {
  const worker = new Worker(new URL("./metadata.worker.ts", import.meta.url), {
    type: "module",
  });
  try {
    const buffer = await file.arrayBuffer();
    if (signal.aborted) throw new DOMException("Cancelled", "AbortError");
    return await new Promise((resolve, reject) => {
      const cleanup = () => {
        clearTimeout(timer);
        signal.removeEventListener("abort", abort);
      };
      const fail = () => {
        cleanup();
        reject(
          new Error(
            "Workbook inspection could not finish. Choose a smaller XLSX or export from Excel.",
          ),
        );
      };
      const abort = () => {
        cleanup();
        reject(new DOMException("Cancelled", "AbortError"));
      };
      const timer = setTimeout(fail, 5000);
      signal.addEventListener("abort", abort, { once: true });
      worker.onerror = fail;
      worker.onmessage = (event) => {
        cleanup();
        if (event.data.error) reject(new Error(event.data.error));
        else resolve(event.data.sheets);
      };
      worker.postMessage(buffer, [buffer]);
    });
  } finally {
    worker.terminate();
  }
}
