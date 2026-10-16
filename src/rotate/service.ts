import RotateWorker from "./rotate.worker?worker&inline";
import { readLocalFile } from "../platform/abort";
import type { CombineInspection } from "../combine/generate";
import { rotateErrors } from "./generate";

async function request(
  file: File,
  turns: number[],
  signal: AbortSignal,
  inspect = false,
) {
  const bytes = await readLocalFile(file, signal);
  if (signal.aborted) throw new Error("Cancelled");
  return new Promise<Uint8Array | CombineInspection>((resolve, reject) => {
    const worker = new RotateWorker();
    const clean = () => {
      signal.removeEventListener("abort", abort);
      worker.onmessage = null;
      worker.onerror = null;
      worker.terminate();
    };
    const abort = () => {
      clean();
      reject(
        new Error("Cancelled. Your original and rotation draft are unchanged."),
      );
    };
    signal.addEventListener("abort", abort, { once: true });
    worker.onerror = (event) => {
      event.preventDefault();
      clean();
      reject(new Error(rotateErrors.output));
    };
    worker.onmessage = (event) => {
      if (event.data.failed) {
        clean();
        const code = event.data.code as keyof typeof rotateErrors;
        reject(
          new Error(
            Object.hasOwn(rotateErrors, code)
              ? rotateErrors[code]
              : rotateErrors.output,
          ),
        );
      } else if (inspect && event.data.result) {
        clean();
        resolve(event.data.result);
      } else if (!inspect && event.data.bytes) {
        clean();
        resolve(event.data.bytes);
      }
    };
    if (signal.aborted) {
      abort();
      return;
    }
    try {
      worker.postMessage({ bytes, turns, inspect }, [bytes.buffer]);
    } catch {
      clean();
      reject(new Error(rotateErrors.output));
    }
  });
}
export async function inspectRotations(file: File, signal: AbortSignal) {
  return (await request(file, [], signal, true)) as CombineInspection;
}
export async function processRotations(
  file: File,
  turns: number[],
  signal: AbortSignal,
) {
  return (await request(file, turns, signal)) as Uint8Array;
}
