import Worker from "./credential.worker?worker&inline";
import { readLocalFile } from "./abort";
export async function credentialCopy(
  file: File,
  confirmed: boolean,
  signal: AbortSignal,
  ordinary = false,
): Promise<Uint8Array | null> {
  const bytes = await readLocalFile(file, signal);
  if (signal.aborted) throw Error("Cancelled");
  return new Promise((resolve, reject) => {
    const worker = new Worker();
    const clean = () => {
      signal.removeEventListener("abort", abort);
      worker.terminate();
    };
    const abort = () => {
      clean();
      reject(Error("Cancelled"));
    };
    signal.addEventListener("abort", abort, { once: true });
    worker.onerror = (e) => {
      e.preventDefault();
      clean();
      reject(Error("Credential copy unavailable"));
    };
    worker.onmessage = (e) => {
      clean();
      if (e.data.ok) resolve(e.data.bytes);
      else reject(Error("Credential copy unavailable"));
    };
    if (signal.aborted) {
      abort();
      return;
    }
    try {
      worker.postMessage({ bytes, confirmed, ordinary }, [bytes.buffer]);
    } catch {
      clean();
      reject(Error("Credential copy unavailable"));
    }
  });
}
