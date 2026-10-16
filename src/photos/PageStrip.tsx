import { useEffect, useRef } from "react";
import type {
  PDFDocumentProxy,
  PDFPageProxy,
  RenderTask,
} from "pdfjs-dist/legacy/build/pdf.mjs";
export function PageStrip({
  doc,
  page,
  disabled,
  select,
  groups,
  selection,
}: {
  groups?: number[][];
  selection?: Set<number>;
  doc: PDFDocumentProxy;
  page: number;
  disabled: boolean;
  select: (page: number) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const root = host.current;
    if (!root) return;
    let stopped = false,
      running = false,
      task: RenderTask | undefined;
    const queue: HTMLButtonElement[] = [],
      queued = new Set<Element>();
    async function drain() {
      if (running) return;
      running = true;
      try {
        while (queue.length && !stopped) {
          const button = queue.shift()!;
          let previewPage: PDFPageProxy | undefined;
          try {
            const p = await doc.getPage(Number(button.dataset.page));
            previewPage = p;
            if (stopped) break;
            const initial = p.getViewport({ scale: 1 }),
              viewport = p.getViewport({
                scale: Math.min(120 / initial.width, 140 / initial.height),
              });
            const canvas = document.createElement("canvas");
            canvas.width = Math.ceil(viewport.width);
            canvas.height = Math.ceil(viewport.height);
            canvas.setAttribute("aria-hidden", "true");
            task = p.render({
              canvas,
              canvasContext: canvas.getContext("2d")!,
              viewport,
              annotationMode: 1,
            });
            await task.promise;
            if (stopped) {
              canvas.width = canvas.height = 0;
              break;
            }
            button.prepend(canvas);
          } catch {
            if (!stopped)
              button.title =
                "Thumbnail unavailable. Open this page to preview.";
          } finally {
            // Retain the small canvas, not every page's full decoded image.
            // PDF.js defers cleanup if this page is also rendering in the main view.
            previewPage?.cleanup();
          }
        }
      } finally {
        running = false;
      }
    }
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting && !queued.has(entry.target)) {
            queued.add(entry.target);
            queue.push(entry.target as HTMLButtonElement);
          }
        }
        void drain();
      },
      { root, rootMargin: "100px" },
    );
    root
      .querySelectorAll("button")
      .forEach((button) => observer.observe(button));
    return () => {
      stopped = true;
      observer.disconnect();
      task?.cancel();
      queue.length = 0;
      root.querySelectorAll("canvas").forEach((c) => {
        c.width = c.height = 0;
        c.remove();
      });
    };
  }, [doc]);
  return (
    <div className="page-strip" ref={host} aria-label="Page thumbnails">
      {Array.from({ length: doc.numPages }, (_, n) => (
        <button
          key={n}
          data-page={n + 1}
          data-part={
            groups ? groups.findIndex((g) => g.includes(n)) + 1 : undefined
          }
          style={
            groups
              ? {
                  borderBottom: `5px solid ${["#b6b6bf", "#3478bc", "#8a56bb", "#21866b", "#c87622"][groups.findIndex((g) => g.includes(n)) < 0 ? 0 : (groups.findIndex((g) => g.includes(n)) % 4) + 1]}`,
                }
              : undefined
          }
          className="secondary"
          disabled={disabled}
          aria-label={`${selection ? "Select" : "Preview"} page ${n + 1}`}
          aria-pressed={selection ? selection.has(n + 1) : undefined}
          aria-current={page === n + 1 ? "page" : undefined}
          onClick={(e) => {
            e.currentTarget.focus();
            select(n + 1);
          }}
        >
          <span>
            {selection && (selection.has(n + 1) ? "✓ " : "○ ")}Page {n + 1}
          </span>
          {groups && (
            <small>
              {groups.some((g) => g.includes(n))
                ? `Part ${groups.findIndex((g) => g.includes(n)) + 1}`
                : "Not included"}
            </small>
          )}
        </button>
      ))}
    </div>
  );
}
