import Worker from "./numbers.worker?worker&inline";
import { readLocalFile } from "../platform/abort";
import { waitForBoot } from "../platform/worker-boot";
import { LIMITS, validateSize } from "../core/contracts";
import type { NumberInspection } from "./generate";
import type { NumberSettings } from "./model";
export async function requestNumbers(
  file: File,
  signal: AbortSignal,
  settings?: NumberSettings,
  font?: Uint8Array,
  stage: (text: string) => void = () => {},
): Promise<NumberInspection | Uint8Array> {
  validateSize(file.size);
  const input = await readLocalFile(file, signal),
    worker = new Worker();
  try {
    await waitForBoot(worker, (data) => data?.ready === true, signal);
  } catch (error) {
    worker.terminate();
    throw error;
  }
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
      worker.terminate();
    };
    const abort = () => {
      cleanup();
      reject(Error("Cancelled. Your PDF and number settings are unchanged."));
    };
    const timer = setTimeout(() => {
      cleanup();
      reject(Error("Numbering took too long. Try a smaller PDF."));
    }, LIMITS.timeoutMs);
    signal.addEventListener("abort", abort, { once: true });
    worker.onerror = (event) => {
      event.preventDefault();
      cleanup();
      reject(
        Error(
          "Page numbering could not finish. Your PDF and settings are unchanged.",
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
    const copy = font?.slice(),
      transfer: Transferable[] = [input.buffer as ArrayBuffer];
    if (copy) transfer.push(copy.buffer as ArrayBuffer);
    try {
      worker.postMessage({ input, settings, font: copy }, transfer);
    } catch {
      cleanup();
      reject(Error("Numbering could not start. Your original is unchanged."));
    }
  });
}
