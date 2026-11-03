import * as pdfjs from "pdfjs-dist/legacy/build/pdf.mjs";
import workerUrl from "pdfjs-dist/legacy/build/pdf.worker.min.mjs?url";
import { ProtectFailure } from "./model";
import { LIMITS } from "../core/contracts";
import { waitForBoot } from "../platform/worker-boot";

let verifierSource: Promise<string> | null = null;
/** Public reader code only. No document, password or result is cached. */
export function prepareVerifier(signal: AbortSignal): Promise<string> {
  if (signal.aborted) return Promise.reject(new ProtectFailure("CANCELLED"));
  if (!verifierSource) {
    const controller = new AbortController(),
      abort = () => controller.abort();
    signal.addEventListener("abort", abort, { once: true });
    const timer = setTimeout(abort, 30000);
    const pending = fetch(workerUrl, {
      signal: controller.signal,
      credentials: "omit",
    })
      .then(async (response) => {
        if (
          !response.ok ||
          Number(response.headers.get("content-length") || 0) > 8 * 1024 * 1024
        )
          throw new ProtectFailure("ENGINE");
        const text = await response.text();
        if (!text || new TextEncoder().encode(text).length > 8 * 1024 * 1024)
          throw new ProtectFailure("ENGINE");
        return URL.createObjectURL(
          new Blob([text], { type: "text/javascript" }),
        );
      })
      .catch(() => {
        if (verifierSource === pending) verifierSource = null;
        throw new ProtectFailure(signal.aborted ? "CANCELLED" : "ENGINE");
      })
      .finally(() => {
        clearTimeout(timer);
        signal.removeEventListener("abort", abort);
      });
    verifierSource = pending;
  }
  const source = verifierSource;
  return new Promise((resolve, reject) => {
    const abort = () => {
      signal.removeEventListener("abort", abort);
      reject(new ProtectFailure("CANCELLED"));
    };
    signal.addEventListener("abort", abort, { once: true });
    source.then(
      (value) => {
        signal.removeEventListener("abort", abort);
        resolve(value);
      },
      (error) => {
        signal.removeEventListener("abort", abort);
        reject(error);
      },
    );
  });
}

/** Independent reader; no renderer, external fonts or document URLs. */
export async function verifyPasswords(
  bytes: ArrayBuffer,
  password: string,
  pages: number,
  signal: AbortSignal,
) {
  const verifierUrl = await prepareVerifier(signal);
  const wrong =
    password === "M11-invalid-password"
      ? "M11-another-invalid"
      : "M11-invalid-password";
  for (const candidate of ["", wrong, password]) {
    if (signal.aborted) throw new ProtectFailure("CANCELLED");
    const port = new Worker(verifierUrl, { type: "module" });
    try {
      await waitForBoot(
        port,
        (data) =>
          data?.sourceName === "worker" &&
          data?.targetName === "main" &&
          data?.action === "ready",
        signal,
      );
    } catch {
      port.terminate();
      throw new ProtectFailure(signal.aborted ? "CANCELLED" : "VERIFY");
    }
    let worker: pdfjs.PDFWorker | undefined;
    let task: pdfjs.PDFDocumentLoadingTask;
    try {
      // @ts-expect-error Upstream declaration omits Worker ports, as in Engine.
      worker = new pdfjs.PDFWorker({ port });
      task = pdfjs.getDocument({
        data: new Uint8Array(bytes.slice(0)),
        password: candidate,
        worker,
        useSystemFonts: false,
        enableXfa: false,
        stopAtErrors: true,
        verbosity: 0,
      });
    } catch {
      try {
        worker?.destroy();
      } finally {
        port.terminate();
      }
      throw new ProtectFailure("VERIFY");
    }
    let timer: ReturnType<typeof setTimeout> | undefined;
    let abort = () => {};
    try {
      const interrupted = new Promise<never>((_, reject) => {
        abort = () => reject(new ProtectFailure("CANCELLED"));
        signal.addEventListener("abort", abort, { once: true });
        timer = setTimeout(
          () => reject(new ProtectFailure("TIMEOUT")),
          LIMITS.timeoutMs,
        );
        if (signal.aborted) abort();
      });
      try {
        const doc = await Promise.race([task.promise, interrupted]);
        if (candidate !== password || doc.numPages !== pages)
          throw new ProtectFailure("VERIFY");
      } catch (error) {
        if (error instanceof ProtectFailure) throw error;
        if (
          candidate === password ||
          !(error instanceof Error) ||
          error.name !== "PasswordException"
        )
          throw new ProtectFailure("VERIFY");
      }
    } finally {
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
      // A stalled reader must not delay cancel or keep its private port alive.
      // Cleanup may await a worker acknowledgement, so do not await it before
      // terminating our independently owned worker.
      try {
        void task.destroy().catch(() => {});
      } finally {
        try {
          worker.destroy();
        } finally {
          port.terminate();
        }
      }
    }
  }
}
