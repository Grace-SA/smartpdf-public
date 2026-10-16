import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import type { RenderTask } from "pdfjs-dist/legacy/build/pdf.mjs";
import type { Engine, Preview } from "../platform/engine";
import type { OrganizeHandle } from "../organize/OrganizePanel";
import { PageDetail } from "../organize/PageDetail";
import { LeaveTaskDialog } from "../LeaveTaskDialog";
import { TaskNotice } from "../TaskNotice";
import { analyticsReason, track } from "../analytics";
import {
  dimensions,
  selectedPages,
  type Dpi,
  type ImageFormat,
  type RasterResult,
} from "./model";
import { exportImages } from "./service";
import { fontWarning } from "./fonts";
import "./raster.css";

function Thumbnail({ preview, index }: { preview: Preview; index: number }) {
  const host = useRef<HTMLSpanElement>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let stopped = false,
      render: RenderTask | undefined;
    let page: Awaited<ReturnType<Preview["doc"]["getPage"]>> | undefined;
    const canvas = document.createElement("canvas");
    void (async () => {
      try {
        page = await preview.doc.getPage(index + 1);
        if (stopped) return;
        const base = page.getViewport({ scale: 1 });
        const viewport = page.getViewport({
          scale: Math.min(140 / base.width, 160 / base.height),
        });
        canvas.width = Math.max(1, Math.ceil(viewport.width));
        canvas.height = Math.max(1, Math.ceil(viewport.height));
        render = page.render({
          canvas,
          canvasContext: canvas.getContext("2d")!,
          viewport,
          annotationMode: 1,
        });
        await render.promise;
        if (!stopped) host.current?.replaceChildren(canvas);
      } catch {
        if (!stopped) setFailed(true);
      } finally {
        page?.cleanup();
      }
    })();
    return () => {
      stopped = true;
      render?.cancel();
      canvas.remove();
      canvas.width = canvas.height = 0;
    };
  }, [preview, index]);
  return (
    <span className="raster-thumb" ref={host}>
      {failed ? "Preview unavailable" : null}
    </span>
  );
}
type Props = {
  file: File;
  preview: Preview;
  engine: Engine;
  publish: (result: RasterResult) => void;
  replace: () => void;
  onClose: () => void;
  onDirty: (v: boolean) => void;
  onBusy: (v: boolean) => void;
};
export const RasterPanel = forwardRef<OrganizeHandle, Props>(
  function RasterPanel(
    { file, preview, engine, publish, replace, onClose, onDirty, onBusy },
    ref,
  ) {
    const [format, setFormat] = useState<ImageFormat>("jpg"),
      [dpi, setDpi] = useState<Dpi>(150);
    const [all, setAll] = useState(true),
      [range, setRange] = useState("");
    const [detail, setDetail] = useState<number | null>(null);
    const [top, setTop] = useState(0),
      [columns, setColumns] = useState(2);
    const [geometry, setGeometry] = useState<{
      key: string;
      ready: boolean;
      error: string;
      size: string;
    }>({ key: "", ready: false, error: "", size: "" });
    const [warning, setWarning] = useState(false),
      [fontReady, setFontReady] = useState(false);
    const [busy, setBusy] = useState(false),
      [progress, setProgress] = useState("");
    const [failure, setFailure] = useState("");
    const [pending, setPending] = useState<{ action: () => void } | null>(null);
    const task = useRef<AbortController | null>(null),
      host = useRef<HTMLDivElement>(null);
    const selection = useMemo(() => {
      try {
        return {
          pages: selectedPages(all ? null : range, preview.doc.numPages),
          error: "",
        };
      } catch (error) {
        return { pages: [] as number[], error: (error as Error).message };
      }
    }, [all, range, preview]);
    useEffect(() => {
      onDirty(true);
      return () => onDirty(false);
    }, [onDirty]);
    useEffect(() => {
      onBusy(busy);
      return () => onBusy(false);
    }, [busy, onBusy]);
    useEffect(() => () => task.current?.abort(), []);
    useEffect(() => {
      const controller = new AbortController();
      void fontWarning(file, controller.signal)
        .then((value) => {
          if (!controller.signal.aborted) {
            setWarning(value);
            setFontReady(true);
          }
        })
        .catch(() => {
          if (!controller.signal.aborted) {
            setWarning(true);
            setFontReady(true);
          }
        });
      return () => controller.abort();
    }, [file]);
    const geometryKey = `${dpi}:${selection.pages.join(",")}`;
    const geometryReady = geometry.key === geometryKey && geometry.ready;
    const geometryError = geometry.key === geometryKey ? geometry.error : "";
    const geometrySize = geometry.key === geometryKey ? geometry.size : "";
    useEffect(() => {
      if (busy) return;
      let stopped = false;

      void (async () => {
        try {
          let size = "",
            mixed = false;
          for (const n of selection.pages) {
            if (stopped) return;
            const page = await preview.doc.getPage(n + 1);
            try {
              const v = page.getViewport({ scale: dpi / 72 });
              let d;
              try {
                d = dimensions(v.width, v.height);
              } catch (error) {
                throw new Error(`Page ${n + 1}: ${(error as Error).message}`, {
                  cause: error,
                });
              }
              const label = `${d.width} × ${d.height} px`;
              if (size && size !== label) mixed = true;
              size ||= label;
            } finally {
              page.cleanup();
            }
          }
          if (!stopped)
            setGeometry({
              key: geometryKey,
              ready: true,
              error: "",
              size: mixed ? "Different sizes follow each PDF page" : size,
            });
        } catch (error) {
          if (!stopped)
            setGeometry({
              key: geometryKey,
              ready: false,
              error: (error as Error).message,
              size: "",
            });
        }
      })();
      return () => {
        stopped = true;
      };
    }, [preview, dpi, selection, busy, geometryKey]);
    useEffect(() => {
      const element = host.current;
      if (!element) return;
      const resize = () =>
        setColumns(Math.max(2, Math.floor(element.clientWidth / 175)));
      const observer = new ResizeObserver(resize);
      observer.observe(element);
      resize();
      return () => observer.disconnect();
    }, [busy]);
    const guard = (action: () => void) => {
      if (task.current) return;
      setPending({ action });
    };
    useImperativeHandle(ref, () => ({ guard }));
    const submit = async () => {
      if (task.current || !geometryReady || !fontReady || selection.error)
        return;
      const controller = new AbortController();
      task.current = controller;
      const started = performance.now();
      let timeout = false;
      const timer = setTimeout(() => {
        timeout = true;
        controller.abort();
      }, 120000);
      setBusy(true);
      setDetail(null);
      setFailure("");
      setProgress("Preparing your images…");
      track("process_start", "raster", {
        pages: selection.pages.length,
        totalBytes: file.size,
      });
      try {
        const result = await exportImages(
          engine,
          file,
          selection.pages,
          dpi,
          format,
          controller.signal,
          setProgress,
        );
        if (controller.signal.aborted) throw new Error("Cancelled");
        track("process_success", "raster", {
          pages: result.count,
          totalBytes: result.file.size,
          durationMs: performance.now() - started,
        });
        publish(result);
      } catch (error) {
        const text = timeout
          ? "This conversion took too long. Choose fewer pages or Standard quality, then try again."
          : controller.signal.aborted
            ? "Cancelled. Your file and settings are unchanged."
            : (error as Error).message;
        setFailure(
          text ||
            "Images could not be created. Try fewer pages or Standard quality.",
        );
        track(
          controller.signal.aborted && !timeout
            ? "process_cancel"
            : "process_failure",
          "raster",
          {
            reason: timeout
              ? "timeout"
              : controller.signal.aborted
                ? "cancelled"
                : analyticsReason(text),
          },
        );
      } finally {
        clearTimeout(timer);
        task.current = null;
        setBusy(false);
      }
    };
    const start = Math.max(0, Math.floor(top / 222) - 1) * columns;
    const end = Math.min(preview.doc.numPages, start + columns * 5);
    const entries = Array.from({ length: preview.doc.numPages }, (_, i) => ({
      id: String(i),
      source: i,
      turns: 0,
      position: i + 1,
    }));
    return (
      <section className="raster-task" aria-label="PDF to images settings">
        <div className="raster-topbar">
          <strong title={file.name}>{file.name}</strong>
          <span>{preview.doc.numPages} pages</span>
          <button
            className="secondary"
            disabled={busy}
            onClick={() => guard(replace)}
          >
            Choose another PDF
          </button>
        </div>
        {warning && (
          <p className="raster-font-notice" role="note">
            Some fonts aren’t embedded or could not be checked. Check the
            preview before converting.
          </p>
        )}
        <div className="raster-layout">
          {!busy && (
            <div
              className="raster-viewport"
              ref={host}
              onScroll={(e) => setTop(e.currentTarget.scrollTop)}
              aria-label="PDF pages"
            >
              <div
                style={{
                  height: Math.ceil(preview.doc.numPages / columns) * 222,
                  position: "relative",
                }}
              >
                {entries.slice(start, end).map((entry) => (
                  <button
                    className="raster-page"
                    data-selected={selection.pages.includes(entry.source)}
                    key={entry.id}
                    style={{
                      position: "absolute",
                      top: Math.floor(entry.source / columns) * 222,
                      left: `${((entry.source % columns) * 100) / columns}%`,
                      width: `${100 / columns}%`,
                    }}
                    onClick={() => setDetail(entry.source)}
                    aria-label={`Preview page ${entry.position}`}
                  >
                    <Thumbnail preview={preview} index={entry.source} />
                    <span>
                      Page {entry.position}
                      {selection.pages.includes(entry.source)
                        ? " · Included"
                        : ""}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}
          <div className="raster-settings">
            <h2>Convert pages to images</h2>
            <fieldset disabled={busy}>
              <legend>Format</legend>
              <div className="raster-options">
                {(["jpg", "png"] as const).map((f) => (
                  <label key={f}>
                    <input
                      type="radio"
                      name="image-format"
                      checked={format === f}
                      onChange={() => setFormat(f)}
                    />
                    <strong>{f.toUpperCase()}</strong>
                    <small>
                      {f === "jpg"
                        ? "Smaller files"
                        : "Sharper text, larger files"}
                    </small>
                  </label>
                ))}
              </div>
            </fieldset>
            <fieldset disabled={busy}>
              <legend>Image quality</legend>
              <div className="raster-options">
                {([150, 300] as const).map((d) => (
                  <label key={d}>
                    <input
                      type="radio"
                      name="image-quality"
                      checked={dpi === d}
                      onChange={() => setDpi(d)}
                    />
                    <strong>{d === 150 ? "Standard" : "High"}</strong>
                    <small>{d} DPI</small>
                  </label>
                ))}
              </div>
            </fieldset>
            <fieldset disabled={busy}>
              <legend>Pages</legend>
              <label>
                <input
                  type="radio"
                  name="page-scope"
                  checked={all}
                  onChange={() => setAll(true)}
                />{" "}
                All pages
              </label>
              <label>
                <input
                  type="radio"
                  name="page-scope"
                  checked={!all}
                  onChange={() => setAll(false)}
                />{" "}
                Page range
              </label>
              {!all && (
                <label className="raster-range">
                  Page range
                  <input
                    aria-label="Page range"
                    value={range}
                    placeholder="1–3, 5"
                    onChange={(e) => setRange(e.target.value)}
                    aria-invalid={!!selection.error}
                  />
                </label>
              )}
            </fieldset>
            {(selection.error || geometryError) && (
              <p role="alert" className="raster-error">
                {selection.error || geometryError}
              </p>
            )}
            {dpi === 300 && geometryError && (
              <button
                className="secondary"
                disabled={busy}
                onClick={() => setDpi(150)}
              >
                Use Standard
              </button>
            )}
            <p className="raster-dimensions">{geometrySize}</p>
            <p className="raster-count">
              {selection.pages.length} pages → {selection.pages.length} images
            </p>
            <div className="raster-submit">
              <button
                disabled={
                  busy || !fontReady || !geometryReady || !!selection.error
                }
                onClick={() => void submit()}
              >
                Convert to {format.toUpperCase()} →
              </button>
              <button
                className="secondary"
                disabled={busy}
                onClick={() => guard(onClose)}
              >
                Cancel task
              </button>
            </div>
          </div>
        </div>
        {detail !== null && !busy && (
          <PageDetail
            preview={preview}
            entries={entries}
            initialIndex={detail}
            close={() => setDetail(null)}
            title="PDF page preview"
          />
        )}
        {pending && (
          <LeaveTaskDialog
            description="Your selected PDF and image settings will be cleared. Your original file won’t be deleted."
            keep={() => setPending(null)}
            leave={() => {
              const action = pending.action;
              setPending(null);
              action();
            }}
          />
        )}
        {busy && (
          <TaskNotice
            working
            title="Creating your images…"
            message={progress}
            close={() => task.current?.abort()}
          />
        )}
        {failure && !busy && (
          <p role="status" className="raster-error">
            {failure}
          </p>
        )}
      </section>
    );
  },
);
