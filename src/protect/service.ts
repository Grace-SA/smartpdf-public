import ProtectWorker from "./protect.worker?worker&inline";
import { LIMITS, ProbeFailure, validateSize } from "../core/contracts";
import { ProtectFailure, PROTECT_ERROR, type ProtectCode } from "./model";
import { qpdfPreparation } from "../platform/qpdf-preparation";
import { prepareVerifier } from "./verify";

const prepareEngine = qpdfPreparation(
  (reason) =>
    new ProtectFailure(reason === "cancelled" ? "CANCELLED" : "ENGINE"),
);
export async function prepareProtect(signal: AbortSignal) {
  await Promise.all([prepareEngine(signal), prepareVerifier(signal)]);
}
function bounded<T>(
  promise: Promise<T>,
  signal: AbortSignal,
  remaining: number,
): Promise<T> {
  if (signal.aborted) return Promise.reject(new ProtectFailure("CANCELLED"));
  return new Promise((resolve, reject) => {
    const clean = () => {
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
    };
    const abort = () => {
      clean();
      reject(new ProtectFailure("CANCELLED"));
    };
    const timer = setTimeout(
      () => {
        clean();
        reject(new ProtectFailure("TIMEOUT"));
      },
      Math.max(1, remaining),
    );
    signal.addEventListener("abort", abort, { once: true });
    promise.then(
      (value) => {
        clean();
        resolve(value);
      },
      (error) => {
        clean();
        reject(error);
      },
    );
  });
}
export async function protectJob(
  file: File,
  password: string | null,
  signal: AbortSignal,
) {
  if (typeof isSecureContext === "boolean" && !isSecureContext)
    throw new ProtectFailure("CONNECTION");
  try {
    validateSize(file.size);
  } catch (error) {
    throw new ProtectFailure(
      error instanceof ProbeFailure && error.code === "INVALID_INPUT"
        ? "INPUT"
        : "RESOURCE",
    );
  }
  if (signal.aborted) throw new ProtectFailure("CANCELLED");
  const encrypting = password !== null;
  const started = Date.now();
  const bytes = await bounded(file.arrayBuffer(), signal, LIMITS.timeoutMs);
  const wasm = encrypting
    ? await bounded(
        prepareEngine(signal),
        signal,
        LIMITS.timeoutMs - (Date.now() - started),
      )
    : null;
  if (signal.aborted) throw new ProtectFailure("CANCELLED");
  return new Promise<{ pages: number; bytes?: ArrayBuffer }>(
    (resolve, reject) => {
      let worker: Worker;
      try {
        worker = new ProtectWorker();
      } catch {
        reject(new ProtectFailure("ENGINE"));
        return;
      }
      let settled = false;
      const finish = (
        error?: ProtectFailure,
        result?: { pages: number; bytes?: ArrayBuffer },
      ) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        signal.removeEventListener("abort", abort);
        worker.onmessage = worker.onerror = worker.onmessageerror = null;
        worker.terminate();
        if (error) reject(error);
        else resolve(result!);
      };
      const abort = () => finish(new ProtectFailure("CANCELLED"));
      const timer = setTimeout(
        () => finish(new ProtectFailure("TIMEOUT")),
        Math.max(1, LIMITS.timeoutMs - (Date.now() - started)),
      );
      signal.addEventListener("abort", abort, { once: true });
      worker.onerror = worker.onmessageerror = () =>
        finish(new ProtectFailure("ENGINE"));
      worker.onmessage = ({ data }: MessageEvent) => {
        if (data?.ok !== true) {
          const code: ProtectCode =
            typeof data?.code === "string" &&
            Object.hasOwn(PROTECT_ERROR, data.code)
              ? data.code
              : "ENGINE";
          finish(new ProtectFailure(code));
          return;
        }
        if (
          !Number.isInteger(data.pages) ||
          data.pages < 1 ||
          data.pages > LIMITS.pages ||
          (encrypting &&
            (!(data.bytes instanceof ArrayBuffer) ||
              !data.bytes.byteLength ||
              data.bytes.byteLength > LIMITS.bytes))
        ) {
          finish(new ProtectFailure("VERIFY"));
          return;
        }
        finish(undefined, { pages: data.pages, bytes: data.bytes });
      };
      if (signal.aborted) {
        abort();
        return;
      }
      const request = {
        kind: password === null ? "inspect" : "protect",
        bytes,
        password,
        wasm: wasm?.slice().buffer,
      };
      try {
        worker.postMessage(
          request,
          request.wasm ? [bytes, request.wasm] : [bytes],
        );
      } catch {
        finish(new ProtectFailure("ENGINE"));
      } finally {
        request.password = "";
        password = "";
      }
    },
  );
}
