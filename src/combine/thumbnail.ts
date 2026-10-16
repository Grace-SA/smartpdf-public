import type { Engine } from "../platform/engine";
import { untilAborted } from "../platform/abort";
/** Render and release one document at a time; keep only a small data URL. */
export async function firstPageThumbnail(
  engine: Engine,
  file: File,
  signal: AbortSignal,
): Promise<string> {
  const preview = await engine.open(file, signal, () => {});
  const canvas = document.createElement("canvas");
  try {
    const page = await untilAborted(preview.doc.getPage(1), signal);
    const base = page.getViewport({ scale: 1 });
    const viewport = page.getViewport({
      scale: Math.min(160 / base.width, 180 / base.height),
    });
    canvas.width = Math.max(1, Math.ceil(viewport.width));
    canvas.height = Math.max(1, Math.ceil(viewport.height));
    const task = page.render({
      canvas,
      canvasContext: canvas.getContext("2d")!,
      viewport,
      annotationMode: 1,
    });
    const abort = () => task.cancel();
    signal.addEventListener("abort", abort, { once: true });
    try {
      await untilAborted(task.promise, signal);
      return canvas.toDataURL("image/png");
    } finally {
      signal.removeEventListener("abort", abort);
      page.cleanup();
    }
  } finally {
    canvas.width = canvas.height = 0;
    await preview.dispose();
  }
}
