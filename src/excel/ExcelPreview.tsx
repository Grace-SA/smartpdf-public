import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { Engine, Preview } from "../platform/engine";
import type { RenderTask } from "pdfjs-dist/legacy/build/pdf.mjs";
import { LIMITS } from "../core/contracts";

/** One rendered page at a time; no spreadsheet HTML approximation or stale frames. */
export function ExcelPreview({ file, engine }: { file: File; engine: Engine }) {
  const [document, setDocument] = useState<Preview>();
  const [page, setPage] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [status, setStatus] = useState("Opening PDF preview…");
  const [width, setWidth] = useState(0);
  const [pixelRatio, setPixelRatio] = useState(1);
  const scroll = useRef<HTMLDivElement>(null);
  const host = useRef<HTMLDivElement>(null);
  const frame = useRef<HTMLCanvasElement | null>(null);
  const active = useRef<RenderTask | undefined>(undefined);
  useLayoutEffect(() => {
    const element = scroll.current;
    if (!element) return;
    const measure = () => {
      setWidth(Math.max(1, Math.round(element.clientWidth)));
      setPixelRatio(Math.max(1, Math.min(3, window.devicePixelRatio || 1)));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    window.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, []);
  useLayoutEffect(() => {
    active.current?.cancel();
    if (frame.current) {
      frame.current.remove();
      frame.current.width = frame.current.height = 0;
      frame.current = null;
    }
  }, [document, page]);
  useEffect(() => {
    const abort = new AbortController();
    let owned: Preview | undefined;
    const timer = setTimeout(() => {
      abort.abort();
      setStatus(
        "Preview took too long. You can still download and check the PDF.",
      );
    }, 30000);
    void engine
      .open(file, abort.signal, setStatus)
      .then((value) => {
        clearTimeout(timer);
        if (abort.signal.aborted) {
          void value.dispose();
          return;
        }
        owned = value;
        setStatus("Rendering page…");
        setDocument(value);
      })
      .catch(() => {
        clearTimeout(timer);
        if (!abort.signal.aborted)
          setStatus(
            "Preview could not open. You can still download and check the PDF.",
          );
      });
    return () => {
      clearTimeout(timer);
      abort.abort();
      const render = active.current;
      render?.cancel();
      void (render?.promise.catch(() => {}) ?? Promise.resolve()).then(() =>
        owned?.dispose(),
      );
    };
  }, [file, engine]);
  useEffect(() => {
    if (!document || !width) return;
    let stopped = false;
    let task: RenderTask | undefined;
    const canvas = window.document.createElement("canvas");
    const timer = setTimeout(() => {
      stopped = true;
      task?.cancel();
      setStatus(
        "This page took too long to render. Download the PDF to check it.",
      );
    }, 30000);
    void (async () => {
      try {
        const pdfPage = await document.doc.getPage(page);
        if (stopped) return;
        const base = pdfPage.getViewport({ scale: 1 });
        const scale = Math.min(
          (width * zoom * pixelRatio) / base.width,
          Math.sqrt(LIMITS.canvasPixels / (base.width * base.height)),
        );
        const viewport = pdfPage.getViewport({ scale });
        canvas.width = Math.max(1, Math.floor(viewport.width));
        canvas.height = Math.max(1, Math.floor(viewport.height));
        canvas.style.width = "100%";
        canvas.style.height = "auto";
        canvas.setAttribute("role", "img");
        canvas.setAttribute("aria-label", `PDF preview, page ${page}`);
        task = pdfPage.render({
          canvas,
          canvasContext: canvas.getContext("2d")!,
          viewport,
          annotationMode: 1,
        });
        active.current = task;
        await task.promise;
        if (stopped) return;
        host.current?.replaceChildren(canvas);
        frame.current = canvas;
        setStatus("");
      } catch {
        if (!stopped)
          setStatus(
            "This page could not render. Download the PDF to check it.",
          );
      } finally {
        clearTimeout(timer);
      }
    })();
    return () => {
      stopped = true;
      clearTimeout(timer);
      task?.cancel();
      if (active.current === task) active.current = undefined;
      if (frame.current === canvas) {
        canvas.remove();
        frame.current = null;
      }
      void (task?.promise.catch(() => {}) ?? Promise.resolve()).then(() => {
        canvas.width = canvas.height = 0;
      });
    };
  }, [document, page, width, zoom, pixelRatio]);
  return (
    <section className="excel-preview" aria-label="Generated PDF preview">
      <div className="word-actions">
        <button
          className="secondary"
          disabled={!document || page <= 1}
          onClick={() => setPage((p) => p - 1)}
        >
          Previous page
        </button>
        <span aria-live="polite">
          Page {page} of {document?.doc.numPages ?? "…"}
        </span>
        <button
          className="secondary"
          disabled={!document || page >= document.doc.numPages}
          onClick={() => setPage((p) => p + 1)}
        >
          Next page
        </button>
        <label>
          Zoom
          <select
            aria-label="Preview zoom"
            value={zoom}
            onChange={(event) => setZoom(Number(event.target.value))}
          >
            <option value="1">Fit width</option>
            <option value="1.5">150%</option>
            <option value="2">200%</option>
            <option value="3">300%</option>
          </select>
        </label>
      </div>
      {status && <p role="status">{status}</p>}
      <div ref={scroll} className="excel-preview-scroll">
        <div ref={host} style={{ width: `${zoom * 100}%` }} />
      </div>
    </section>
  );
}
