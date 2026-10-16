import Worker from "./sign.worker?worker&inline";
import { readLocalFile } from "../platform/abort";
import { LIMITS, validateSize } from "../core/contracts";
import type { Geometry, Placement, SignatureAsset } from "./model";
const sources = new WeakMap<File, Uint8Array>();
export async function requestSign(
  file: File,
  signal: AbortSignal,
  assets: SignatureAsset[] = [],
  placements: Placement[] = [],
  stage: (s: string) => void = () => {},
): Promise<Geometry[] | Uint8Array> {
  validateSize(file.size);
  let source = sources.get(file);
  if (!source) {
    source = await readLocalFile(file, signal);
    sources.set(file, source);
  }
  const bytes = source.slice();
  return new Promise((resolve, reject) => {
    const worker = new Worker();
    const clean = () => {
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
      worker.terminate();
    };
    const abort = () => {
      clean();
      reject(Error("Cancelled. Your signature draft is unchanged."));
    };
    const timer = setTimeout(() => {
      clean();
      reject(
        Error(
          "Signing took too long. Try a smaller PDF. Your draft is unchanged.",
        ),
      );
    }, LIMITS.timeoutMs);
    signal.addEventListener("abort", abort, { once: true });
    worker.onerror = (e) => {
      e.preventDefault();
      clean();
      reject(Error("Signing could not finish. Your draft is unchanged."));
    };
    worker.onmessage = (e) => {
      if (e.data.stage) {
        stage(e.data.stage);
        return;
      }
      clean();
      if (e.data.error) reject(Error(e.data.error));
      else resolve(e.data.geometry ?? e.data.bytes);
    };
    if (signal.aborted) {
      abort();
      return;
    }
    try {
      worker.postMessage(
        {
          bytes,
          inspect: !placements.length,
          assets: assets.map((a) => ({ id: a.id, bytes: a.bytes })),
          placements,
        },
        [bytes.buffer],
      );
    } catch {
      clean();
      reject(Error("Signing could not start. Your draft is unchanged."));
    }
  });
}
