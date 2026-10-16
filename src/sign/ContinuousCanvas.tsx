import { useEffect, useRef, useState } from "react";
import type { RenderTask } from "pdfjs-dist/legacy/build/pdf.mjs";
import type { Preview } from "../platform/engine";

// Across mounted pages: at most two render jobs, five displayed canvases.
let running = 0;
const waiting: (() => void)[] = [];
export async function acquirePageRender(signal: AbortSignal) {
  await new Promise<void>((resolve, reject) => {
    const abort = () => {
      const i = waiting.indexOf(start);
      if (i >= 0) waiting.splice(i, 1);
      reject(new DOMException("Cancelled", "AbortError"));
    };
    const start = () => {
      signal.removeEventListener("abort", abort);
      running++;
      resolve();
    };
    if (signal.aborted) {
      reject(new DOMException("Cancelled", "AbortError"));
      return;
    }
    if (running < 2) start();
    else {
      waiting.push(start);
      signal.addEventListener("abort", abort, { once: true });
    }
  });
  return () => {
    running--;
    waiting.shift()?.();
  };
}
export function ContinuousCanvas({
  preview,
  index,
  width,
  height,
  active,
  ready,
}: {
  preview: Preview;
  index: number;
  width: number;
  height: number;
  active: boolean;
  ready: (index: number, value: boolean) => void;
}) {
  const host = useRef<HTMLDivElement>(null),
    shown = useRef<HTMLCanvasElement | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    if (!active) {
      shown.current?.remove();
      if (shown.current) shown.current.width = shown.current.height = 0;
      shown.current = null;
      ready(index, false);
      return;
    }
    const controller = new AbortController(),
      canvas = document.createElement("canvas");
    let task: RenderTask | undefined;
    void (async () => {
      let release: (() => void) | undefined;
      try {
        release = await acquirePageRender(controller.signal);
        if (controller.signal.aborted) return;
        setError(false);
        const page = await preview.doc.getPage(index + 1);
        if (controller.signal.aborted) return;
        const base = page.getViewport({ scale: 1 });
        const ratio = Math.min(
          devicePixelRatio || 1,
          2,
          Math.sqrt(1_800_000 / (width * height)),
        );
        const viewport = page.getViewport({
          scale: (width / base.width) * ratio,
        });
        canvas.width = Math.max(1, Math.floor(viewport.width));
        canvas.height = Math.max(1, Math.floor(viewport.height));
        canvas.style.width = "100%";
        canvas.style.height = "100%";
        task = page.render({
          canvas,
          canvasContext: canvas.getContext("2d")!,
          viewport,
          annotationMode: 1,
        });
        await task.promise;
        if (controller.signal.aborted) return;
        const old = shown.current;
        host.current?.replaceChildren(canvas);
        shown.current = canvas;
        if (old) old.width = old.height = 0;
        ready(index, true);
      } catch {
        if (!controller.signal.aborted) setError(true);
      } finally {
        if (shown.current !== canvas) canvas.width = canvas.height = 0;
        release?.();
      }
    })();
    return () => {
      controller.abort();
      task?.cancel();
    };
  }, [preview, index, width, height, active, ready]);
  useEffect(
    () => () => {
      if (shown.current) shown.current.width = shown.current.height = 0;
    },
    [],
  );
  return (
    <>
      <div className="sign-canvas" ref={host} />
      {error && (
        <span className="sign-page-error" role="status">
          This page could not be displayed.
        </span>
      )}
    </>
  );
}
