import { parentPort, workerData } from "node:worker_threads";
import { readFile } from "node:fs/promises";
import { PDFDocument } from "pdf-lib";

try {
  const bytes = await readFile(workerData);
  if (bytes.length > 30 * 1024 ** 2) throw new Error("limit");
  const pdf = await PDFDocument.load(bytes, { updateMetadata: false });
  const pages = pdf.getPages();
  if (
    !pages.length ||
    pages.length > 200 ||
    pages.some((p) => {
      const { width, height } = p.getSize();
      return (
        !Number.isFinite(width + height) ||
        width < 1 ||
        height < 1 ||
        width > 14400 ||
        height > 14400
      );
    })
  )
    throw new Error("limit");
  parentPort.postMessage({ pages: pages.length });
} catch {
  parentPort.postMessage({ error: true });
}
