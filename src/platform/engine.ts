import * as pdfjs from "pdfjs-dist/legacy/build/pdf.mjs";
import pdfWorkerUrl from "pdfjs-dist/legacy/build/pdf.worker.min.mjs?url";
import ProbeWorker from "./probe.worker?worker&inline";
import { readLocalFile, untilAborted } from "./abort";
import { waitForBoot } from "./worker-boot";
import { installMemoryResources, resourceOrigin } from "./memory-resources";
import {
  LIMITS,
  ProbeFailure,
  validateSize,
  type ProbeResult,
  type Reason,
} from "../core/contracts";

export type Preview = {
  doc: pdfjs.PDFDocumentProxy;
  worker: pdfjs.PDFWorker;
  port: Worker;
  name: string;
  byteLength: number;
  previewFeatures: Reason[];
  dispose: () => Promise<void>;
};
type ResourcePack = Record<string, Uint8Array>;
export class Engine {
  private workerUrl = "";
  private resources: ResourcePack = {};
  private sequence = 0;

  async prepare(signal?: AbortSignal): Promise<void> {
    const [scriptResponse, dataResponse] = await Promise.all([
      fetch(pdfWorkerUrl, { signal }),
      fetch("/pdf-resources.json", { signal }),
    ]);
    if (!scriptResponse.ok || !dataResponse.ok)
      throw new Error("RESOURCE_LOAD_FAILED");
    const [script, pack] = await Promise.all([
      scriptResponse.text(),
      dataResponse.json() as Promise<Record<string, string>>,
    ]);
    const resources: ResourcePack = {};
    for (const [key, value] of Object.entries(pack))
      resources[key] = Uint8Array.from(atob(value), (c) => c.charCodeAt(0));
    if (signal?.aborted) throw new ProbeFailure("CANCELLED");
    this.resources = resources;
    this.workerUrl = URL.createObjectURL(
      new Blob([`(${installMemoryResources.toString()})();\n`, script], {
        type: "text/javascript",
      }),
    );
    // Confirm both engines can boot before enabling the file chooser.
    try {
      const probe = new ProbeWorker();
      try {
        await waitForBoot(probe, (data) => data?.ready === true, signal);
      } finally {
        probe.terminate();
      }
      const port = new Worker(this.workerUrl, { type: "module" });
      try {
        // External PDFWorker.promise only confirms attachment, not boot.
        // PDF.js 6.4.299 sends this packet after initializeFromPort setup.
        await waitForBoot(
          port,
          (data) =>
            data?.sourceName === "worker" &&
            data?.targetName === "main" &&
            data?.action === "ready",
          signal,
        );
      } finally {
        port.terminate();
      }
    } catch (error) {
      this.dispose();
      throw error;
    }
  }

  dispose(): void {
    if (this.workerUrl) URL.revokeObjectURL(this.workerUrl);
    this.workerUrl = "";
    this.resources = {};
  }

  private async renderingWorker(signal: AbortSignal): Promise<Worker> {
    const port = new Worker(this.workerUrl, { type: "module" });
    try {
      // A resource acknowledgement alone can precede PDF.js initialization.
      // Confirm this instance's request handler before attaching a document.
      await waitForBoot(
        port,
        (data) =>
          data?.sourceName === "worker" &&
          data?.targetName === "main" &&
          data?.action === "ready",
        signal,
      );
      await waitForBoot(
        port,
        (data) => data?.smartPdfResourcesReady === true,
        signal,
        () => port.postMessage({ smartPdfResources: this.resources }),
      );
      return port;
    } catch (error) {
      port.terminate();
      throw error;
    }
  }

  private async probe(
    bytes: Uint8Array,
    signal: AbortSignal,
  ): Promise<ProbeResult> {
    const worker = new ProbeWorker();
    try {
      // Every newly created probe must be ready, not just the startup canary.
      await waitForBoot(worker, (data) => data?.ready === true, signal);
    } catch (error) {
      worker.terminate();
      throw error instanceof ProbeFailure
        ? error
        : new ProbeFailure("PROCESSING_FAILED");
    }
    const id = ++this.sequence;
    return new Promise((resolve, reject) => {
      let cleaned = false;
      const clean = () => {
        if (cleaned) return;
        cleaned = true;
        worker.onmessage = null;
        worker.onerror = null;
        worker.terminate();
        signal.removeEventListener("abort", abort);
      };
      const abort = () => {
        clean();
        reject(new ProbeFailure("CANCELLED"));
      };
      signal.addEventListener("abort", abort, { once: true });
      if (signal.aborted) {
        abort();
        return;
      }
      worker.onerror = (event) => {
        event.preventDefault();
        clean();
        reject(new ProbeFailure("PROCESSING_FAILED"));
      };
      worker.onmessage = (
        event: MessageEvent<{ id?: number; result: ProbeResult }>,
      ) => {
        if (event.data.id !== id) return;
        clean();
        resolve(event.data.result);
      };
      // Transfer a copy: the immutable input remains available for independent rendering.
      try {
        const copy = bytes.slice();
        worker.postMessage({ id, bytes: copy }, [copy.buffer]);
      } catch {
        clean();
        reject(new ProbeFailure("PROCESSING_FAILED"));
      }
    });
  }

  async open(
    file: File,
    signal: AbortSignal,
    stage: (text: string) => void,
    profile: "preview" | "raster" = "preview",
  ): Promise<Preview> {
    validateSize(file.size);
    if (!/\.pdf$/i.test(file.name))
      throw new ProbeFailure("INVALID_INPUT", "malformed");
    stage("Reading your file…");
    const bytes = await readLocalFile(file, signal);
    if (signal.aborted) throw new ProbeFailure("CANCELLED");
    stage("Checking document structure…");
    const result = await this.probe(bytes, signal);
    if (!result.ok)
      throw new ProbeFailure(result.code, result.reason, result.reasons);
    stage("Preparing the first page…");
    const resources = this.resources;
    class MemoryBinaryDataFactory {
      async fetch({
        kind,
        filename,
      }: {
        kind: string;
        filename: string;
      }): Promise<Uint8Array> {
        const data = resources[`${kind}/${filename}`];
        if (!data) throw new Error("RESOURCE_NOT_PRELOADED");
        return data.slice();
      }
    }
    const port = await this.renderingWorker(signal);
    let worker: pdfjs.PDFWorker | undefined;
    let task: pdfjs.PDFDocumentLoadingTask;
    try {
      // @ts-expect-error Upstream declaration omits Worker ports.
      worker = new pdfjs.PDFWorker({ port });
      task = pdfjs.getDocument({
        data: bytes,
        worker,
        BinaryDataFactory: MemoryBinaryDataFactory,
        cMapUrl: resourceOrigin + "cMapUrl/",
        cMapPacked: true,
        standardFontDataUrl: resourceOrigin + "standardFontDataUrl/",
        wasmUrl: resourceOrigin + "wasmUrl/",
        iccUrl: resourceOrigin + "iccUrl/",
        useWorkerFetch: true,
        useWasm: true,
        useSystemFonts: false,
        enableXfa: false,
        stopAtErrors: true,
        maxImageSize: LIMITS.jpegPixels,
        canvasMaxAreaInBytes:
          (profile === "raster" ? 10_000_000 : LIMITS.canvasPixels) * 4,
        verbosity: 0,
      });
    } catch (error) {
      worker?.destroy();
      port.terminate();
      throw error;
    }
    let disposed = false;
    const dispose = async () => {
      if (disposed) return;
      disposed = true;
      try {
        await task.destroy();
      } finally {
        worker?.destroy();
        port.terminate();
      }
    };
    const abort = () => {
      void dispose();
    };
    signal.addEventListener("abort", abort, { once: true });
    try {
      if (signal.aborted) throw new ProbeFailure("CANCELLED");
      const doc = await untilAborted(task.promise, signal);
      if (signal.aborted) throw new ProbeFailure("CANCELLED");
      if (doc.numPages !== result.pages)
        throw new ProbeFailure("INVALID_INPUT", "malformed");
      return {
        doc,
        worker: worker!,
        port,
        name: file.name,
        byteLength: file.size,
        previewFeatures: result.previewFeatures ?? [],
        dispose,
      };
    } catch (error) {
      await dispose();
      throw error;
    } finally {
      signal.removeEventListener("abort", abort);
    }
  }
}

export async function renderPage(
  preview: Preview,
  pageNumber: number,
  signal: AbortSignal,
): Promise<{ canvas: HTMLCanvasElement; text: string }> {
  const page = await untilAborted(preview.doc.getPage(pageNumber), signal);
  if (signal.aborted) throw new ProbeFailure("CANCELLED");
  const base = page.getViewport({ scale: 1 });
  const scale = Math.min(
    1.6,
    Math.sqrt(LIMITS.canvasPixels / (base.width * base.height)),
  );
  const viewport = page.getViewport({ scale });
  const canvas = document.createElement("canvas");
  canvas.width = Math.floor(viewport.width);
  canvas.height = Math.floor(viewport.height);
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", `PDF preview, page ${pageNumber}`);
  const context = canvas.getContext("2d");
  if (!context) throw new ProbeFailure("RESOURCE_LIMIT");
  const task = page.render({
    canvas,
    canvasContext: context,
    viewport,
    // Paint link appearances, but never construct interactive annotation DOM.
    annotationMode: pdfjs.AnnotationMode.ENABLE,
  });
  const abort = () => task.cancel();
  signal.addEventListener("abort", abort, { once: true });
  try {
    await task.promise;
    // PDF.js getTextContent uses ReadableStream async iteration, absent on
    // Safari/iOS 18 even in the legacy build. Consume its public stream with
    // a reader so preview and accessible text remain available there.
    const reader = page.streamTextContent().getReader();
    const text: string[] = [];
    let done = false;
    const cancelText = () => {
      void reader.cancel().catch(() => undefined);
    };
    signal.addEventListener("abort", cancelText, { once: true });
    try {
      while (!done) {
        if (signal.aborted) throw new ProbeFailure("CANCELLED");
        const chunk = await untilAborted(reader.read(), signal);
        done = chunk.done;
        if (!done)
          for (const item of chunk.value.items)
            text.push("str" in item ? item.str : "");
      }
      if (signal.aborted) throw new ProbeFailure("CANCELLED");
    } finally {
      signal.removeEventListener("abort", cancelText);
      if (!done) cancelText();
      reader.releaseLock();
    }
    return {
      canvas,
      text: text.join(" "),
    };
  } catch (error) {
    canvas.width = 0;
    canvas.height = 0;
    throw error;
  } finally {
    signal.removeEventListener("abort", abort);
    page.cleanup();
  }
}
