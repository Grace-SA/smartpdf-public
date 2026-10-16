import type { Engine, Preview } from "../platform/engine";
import { untilAborted } from "../platform/abort";
import { density } from "./density";
import {
  archiveName,
  dimensions,
  imageName,
  RASTER,
  type Dpi,
  type ImageFormat,
  type RasterResult,
} from "./model";
import { zipFiles } from "../downloads/zip";
import type { RenderTask } from "pdfjs-dist/legacy/build/pdf.mjs";

const check = (signal: AbortSignal) => {
  if (signal.aborted) throw new Error("Cancelled");
};
export function encodeImage(
  canvas: HTMLCanvasElement,
  type: string,
  signal: AbortSignal,
) {
  return new Promise<Blob>((resolve, reject) => {
    const abort = () => reject(new Error("Cancelled"));
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) {
      signal.removeEventListener("abort", abort);
      abort();
      return;
    }
    try {
      canvas.toBlob(
        (blob) => {
          signal.removeEventListener("abort", abort);
          if (signal.aborted) reject(new Error("Cancelled"));
          else if (!blob || blob.type !== type)
            reject(
              new Error(
                "This browser could not create this image format. Try the other format.",
              ),
            );
          else resolve(blob);
        },
        type,
        0.9,
      );
    } catch (error) {
      signal.removeEventListener("abort", abort);
      reject(error);
    }
  });
}
export async function exportImages(
  engine: Engine,
  source: File,
  pages: number[],
  dpi: Dpi,
  format: ImageFormat,
  signal: AbortSignal,
  progress: (text: string) => void,
): Promise<RasterResult> {
  let preview: Preview | undefined;
  const files: File[] = [];
  let bytes = source.size;
  try {
    check(signal);
    if (
      !pages.length ||
      pages.length > 200 ||
      new Set(pages).size !== pages.length
    )
      throw new Error("Choose a valid page range.");
    preview = await engine.open(source, signal, progress, "raster");
    for (const n of pages) {
      check(signal);
      if (!Number.isInteger(n) || n < 0 || n >= preview.doc.numPages)
        throw new Error("Choose a valid page range.");
      const page = await untilAborted(preview.doc.getPage(n + 1), signal);
      try {
        const v = page.getViewport({ scale: dpi / 72 });
        dimensions(v.width, v.height);
      } finally {
        page.cleanup();
      }
    }
    const mime = format === "jpg" ? "image/jpeg" : "image/png";
    for (const [i, n] of pages.entries()) {
      check(signal);
      progress(`Converting page ${i + 1} of ${pages.length}…`);
      const page = await untilAborted(preview.doc.getPage(n + 1), signal);
      const canvas = document.createElement("canvas");
      let render: RenderTask | undefined;
      const abort = () => render?.cancel();
      signal.addEventListener("abort", abort, { once: true });
      try {
        const viewport = page.getViewport({ scale: dpi / 72 });
        const size = dimensions(viewport.width, viewport.height);
        canvas.width = size.width;
        canvas.height = size.height;
        const context = canvas.getContext("2d", { alpha: false });
        if (!context)
          throw new Error(
            "Not enough memory to create this image. Choose Standard or fewer pages.",
          );
        check(signal);
        render = page.render({
          canvas,
          canvasContext: context,
          viewport,
          background: "rgb(255,255,255)",
          annotationMode: 1,
        });
        await untilAborted(render.promise, signal);
        const encoded = await encodeImage(canvas, mime, signal);
        check(signal);
        if (bytes + encoded.size + 64 > RASTER.bytes)
          throw new Error(
            "Images exceed the download limit. Use Standard, JPG or fewer pages.",
          );
        const blob = await untilAborted(density(encoded, dpi), signal);
        bytes += blob.size;
        if (bytes > RASTER.bytes)
          throw new Error(
            "Images exceed the download limit. Use Standard, JPG or fewer pages.",
          );
        files.push(
          new File([blob], imageName(source.name, n + 1, format), {
            type: mime,
          }),
        );
      } finally {
        signal.removeEventListener("abort", abort);
        render?.cancel();
        canvas.width = canvas.height = 0;
        page.cleanup();
      }
      await untilAborted(new Promise<void>((r) => setTimeout(r, 0)), signal);
    }
    check(signal);
    if (files.length === 1) return { file: files[0]!, count: 1, format };
    progress("Preparing download…");
    const zip = await zipFiles(files, {
      maxFiles: 200,
      maxBytes: RASTER.bytes - source.size,
      signal,
    });
    check(signal);
    return {
      file: new File([zip], archiveName(source.name), {
        type: "application/zip",
      }),
      count: files.length,
      format,
    };
  } finally {
    files.length = 0;
    await preview?.dispose();
  }
}
