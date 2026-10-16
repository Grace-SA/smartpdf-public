import Worker from "./watermark.worker?worker&inline";
import { readLocalFile } from "../platform/abort";
import { LIMITS, validateSize } from "../core/contracts";
import type { WatermarkInspection, WatermarkImage } from "./generate";
import type { WatermarkSettings } from "./model";
export async function requestWatermark(
  file: File,
  signal: AbortSignal,
  settings?: WatermarkSettings,
  font?: Uint8Array,
  image?: WatermarkImage,
  stage: (text: string) => void = () => {},
): Promise<WatermarkInspection | Uint8Array> {
  validateSize(file.size);
  const input = await readLocalFile(file, signal);
  return new Promise((resolve, reject) => {
    const worker = new Worker();
    const cleanup = () => {
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
      worker.terminate();
    };
    const abort = () => {
      cleanup();
      reject(
        Error("Cancelled. Your PDF and watermark settings are unchanged."),
      );
    };
    const timer = setTimeout(() => {
      cleanup();
      reject(
        Error("Watermarking took too long. Try fewer pages or a smaller PDF."),
      );
    }, LIMITS.timeoutMs);
    signal.addEventListener("abort", abort, { once: true });
    worker.onerror = (event) => {
      event.preventDefault();
      cleanup();
      reject(
        Error(
          "Watermarking could not finish. Your PDF and settings are unchanged.",
        ),
      );
    };
    worker.onmessage = (event) => {
      if (event.data.stage) {
        stage(event.data.stage);
        return;
      }
      cleanup();
      if (event.data.error) reject(Error(event.data.error));
      else resolve(event.data.inspection ?? event.data.output);
    };
    if (signal.aborted) {
      abort();
      return;
    }
    const fontCopy = font?.slice(),
      imageCopy = image ? { ...image, bytes: image.bytes.slice() } : undefined;
    const transfer: Transferable[] = [input.buffer as ArrayBuffer];
    if (fontCopy) transfer.push(fontCopy.buffer as ArrayBuffer);
    if (imageCopy) transfer.push(imageCopy.bytes.buffer as ArrayBuffer);
    try {
      worker.postMessage(
        {
          input,
          inspect: !settings,
          settings,
          font: fontCopy,
          image: imageCopy,
        },
        transfer,
      );
    } catch {
      cleanup();
      reject(
        Error("Watermarking could not start. Your original is unchanged."),
      );
    }
  });
}
