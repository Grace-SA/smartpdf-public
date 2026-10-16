import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { PreviewDialog } from "../PreviewDialog";
import type { RenderTask } from "pdfjs-dist/legacy/build/pdf.mjs";
import type { Preview } from "../platform/engine";
import { LIMITS } from "../core/contracts";
import type { PageEntry } from "./model";

export function PageDetail({
  preview,
  entries,
  close,
  initialIndex = 0,
  title,
}: {
  preview: Preview;
  entries: (PageEntry & { position: number })[];
  close: () => void;
  initialIndex?: number;
  title?: string;
}) {
  const host = useRef<HTMLDivElement>(null);
  const displayed = useRef<HTMLCanvasElement | null>(null);
  const [index, setIndex] = useState(initialIndex),
    [zoom, setZoom] = useState(1),
    [size, setSize] = useState({
      width: window.innerWidth,
      height: window.innerHeight,
    }),
    [status, setStatus] = useState("Loading page…");
  const entry = entries[index]!;
  useLayoutEffect(() => {
    // A retained frame is only valid for the same document, page and rotation.
    // Clear it before painting a new page title, including failed/slow renders.
    const previous = displayed.current;
    if (previous) {
      previous.remove();
      previous.width = previous.height = 0;
    }
    displayed.current = null;
  }, [preview, entry.source, entry.turns]);
  useEffect(() => {
    const element = host.current!;
    const resize = () => {
      // Measure the container, not the area left after transient scrollbars.
      const rect = element.getBoundingClientRect();
      const width = Math.round(rect.width),
        height = Math.round(rect.height);
      setSize((old) =>
        old.width === width && old.height === height ? old : { width, height },
      );
    };
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    resize();
    return () => {
      observer.disconnect();
      if (displayed.current)
        displayed.current.width = displayed.current.height = 0;
      displayed.current = null;
    };
  }, []);
  useEffect(() => {
    let stopped = false,
      render: RenderTask | undefined;
    const canvas = document.createElement("canvas");
    const timer = window.setTimeout(() => {
      stopped = true;
      render?.cancel();
      canvas.width = canvas.height = 0;
      setStatus("This page took too long to display. Close and try again.");
    }, LIMITS.timeoutMs);
    void (async () => {
      let page;
      try {
        setStatus("Loading page…");
        page = await preview.doc.getPage(entry.source + 1);
        if (stopped) return;
        const rotation = (page.rotate + entry.turns * 90) % 360;
        const base = page.getViewport({ scale: 1, rotation });
        const widthScale =
          Math.max(100, size.width - (size.width < 640 ? 24 : 100)) /
          base.width;
        const cssScale =
          zoom === 0
            ? Math.min(
                widthScale,
                Math.max(100, size.height - 24) / base.height,
              )
            : widthScale * zoom;
        const scale = Math.min(
          cssScale * Math.min(window.devicePixelRatio || 1, 2),
          Math.sqrt(LIMITS.canvasPixels / (base.width * base.height)),
        );
        const viewport = page.getViewport({ scale, rotation });
        canvas.width = Math.max(1, Math.floor(viewport.width));
        canvas.height = Math.max(1, Math.floor(viewport.height));
        canvas.style.width = `${base.width * cssScale}px`;
        canvas.style.height = `${base.height * cssScale}px`;
        canvas.setAttribute(
          "aria-label",
          `Original page ${entry.source + 1}, ${entry.turns * 90} degrees added rotation`,
        );
        render = page.render({
          canvas,
          canvasContext: canvas.getContext("2d")!,
          viewport,
          annotationMode: 1,
        });
        await render.promise;
        if (!stopped) {
          const previous = displayed.current;
          host.current?.replaceChildren(canvas);
          displayed.current = canvas;
          if (previous) previous.width = previous.height = 0;
          if (host.current) {
            host.current.scrollTop = 0;
            host.current.scrollLeft = 0;
          }
          setStatus("");
        }
      } catch {
        if (!stopped)
          setStatus(
            "This page could not be enlarged. Your draft is unchanged.",
          );
      } finally {
        clearTimeout(timer);
        page?.cleanup();
      }
    })();
    return () => {
      stopped = true;
      clearTimeout(timer);
      render?.cancel();
      // Same-page resizing keeps its complete frame until replacement is ready.
      if (displayed.current !== canvas) {
        canvas.width = canvas.height = 0;
        canvas.remove();
      }
    };
  }, [preview, entry.source, entry.turns, size, zoom]);
  return (
    <PreviewDialog
      label="Enlarged selected page"
      title={
        title ? `${title} · Page ${entry.position}` : `Page ${entry.position}`
      }
      close={close}
      previous={index > 0 ? () => setIndex(index - 1) : undefined}
      next={index < entries.length - 1 ? () => setIndex(index + 1) : undefined}
      toolbar={
        <>
          <label>
            Page
            <select
              aria-label="Page number"
              value={index}
              onChange={(event) => setIndex(Number(event.target.value))}
            >
              {entries.map((item, i) => (
                <option key={`${item.id}-${i}`} value={i}>
                  {i + 1} / {entries.length}
                </option>
              ))}
            </select>
          </label>
          <label>
            Zoom{" "}
            <select
              value={zoom}
              onChange={(e) => setZoom(Number(e.target.value))}
            >
              <option value={0}>Fit page</option>
              <option value={1}>Fit width</option>
              <option value={2}>200%</option>
            </select>
          </label>
        </>
      }
    >
      {status && (
        <p className="lightbox-status" role="status">
          {status}
        </p>
      )}
      <div
        className="page-detail-canvas"
        ref={host}
        tabIndex={0}
        aria-label="Scrollable enlarged page"
      />
    </PreviewDialog>
  );
}
