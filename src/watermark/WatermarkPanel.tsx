import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { Preview } from "../platform/engine";
import type { OrganizeHandle } from "../organize/OrganizePanel";
import { ContinuousCanvas } from "../sign/ContinuousCanvas";
import {
  readingLayout,
  readingPage,
  readingWindow,
} from "../sign/reading-layout";
import { displaySize } from "../overlay/geometry";
import { FilePicker } from "../FilePicker";
import { LeaveTaskDialog } from "../LeaveTaskDialog";
import { TaskNotice } from "../TaskNotice";
import { PHOTO_LIMITS, safeFilename } from "../photos/model";
import { analyticsReason, track } from "../analytics";
import { prepareWatermark, textShape } from "./font";
import { defaults, planWatermarks, type WatermarkSettings } from "./model";
import { watermarkImage, type ImageAsset } from "./image";
import { requestWatermark } from "./service";
import type { WatermarkInspection } from "./generate";
import "./watermark.css";
type Props = {
  file: File;
  preview: Preview;
  pageIds: string[];
  retainedFiles: File[];
  apply: (file: File, ids: string[], signal: AbortSignal) => Promise<boolean>;
  onClose: () => void;
  onDirty: (value: boolean) => void;
  onBusy: (value: boolean) => void;
};
const positions = [
  "Top left",
  "Top center",
  "Top right",
  "Middle left",
  "Center",
  "Middle right",
  "Bottom left",
  "Bottom center",
  "Bottom right",
];
export const WatermarkPanel = forwardRef<OrganizeHandle, Props>(
  function WatermarkPanel(props, ref) {
    const [settings, setSettings] = useState<WatermarkSettings>({
      ...defaults,
    });
    const [inspection, setInspection] = useState<WatermarkInspection | null>(
        null,
      ),
      [font, setFont] = useState<Uint8Array | null>(null);
    const [initialising, setInitialising] = useState(true),
      [initialError, setInitialError] = useState(""),
      [retry, setRetry] = useState(0);
    const [asset, setAsset] = useState<ImageAsset | null>(null),
      [busy, setBusy] = useState(false),
      [stage, setStage] = useState(""),
      [failure, setFailure] = useState("");
    const [pending, setPending] = useState<{ action: () => void } | null>(null);
    const job = useRef<AbortController | null>(null),
      viewport = useRef<HTMLDivElement>(null);
    const [dimensions, setDimensions] = useState({ width: 560, height: 560 }),
      [zoom, setZoom] = useState(-1),
      [page, setPage] = useState(0),
      [scrollTop, setScrollTop] = useState(0),
      [pageError, setPageError] = useState("");
    const [readyPages, setReadyPages] = useState(new Set<number>());
    const ready = useCallback(
      (index: number, value: boolean) =>
        setReadyPages((old) => {
          if (old.has(index) === value) return old;
          const next = new Set(old);
          if (value) next.add(index);
          else next.delete(index);
          return next;
        }),
      [],
    );
    const { onBusy, onDirty } = props;
    useEffect(() => {
      onDirty(true);
      return () => onDirty(false);
    }, [onDirty]);
    useEffect(() => {
      onBusy(initialising || busy);
      return () => onBusy(false);
    }, [initialising, busy, onBusy]);
    useEffect(() => () => job.current?.abort(), []);
    useEffect(
      () => () => {
        if (asset) URL.revokeObjectURL(asset.url);
      },
      [asset],
    );
    useEffect(() => {
      const controller = new AbortController();
      job.current = controller;
      void Promise.all([
        requestWatermark(props.file, controller.signal),
        prepareWatermark(controller.signal),
      ])
        .then(([value, bytes]) => {
          if (controller.signal.aborted) return;
          if (value instanceof Uint8Array)
            throw Error("PDF inspection failed.");
          setInspection(value);
          setFont(bytes);
        })
        .catch((error) => {
          if (!controller.signal.aborted)
            setInitialError((error as Error).message);
        })
        .finally(() => {
          if (job.current === controller) {
            job.current = null;
            setInitialising(false);
          }
        });
      return () => controller.abort();
    }, [props.file, retry]);
    useEffect(() => {
      const node = viewport.current;
      if (!node) return;
      const resize = () =>
        setDimensions({
          width: Math.max(100, node.clientWidth - 40),
          height: Math.max(100, node.clientHeight - 16),
        });
      const observer = new ResizeObserver(resize);
      observer.observe(node);
      resize();
      return () => observer.disconnect();
    }, []);
    function guard(action: () => void) {
      if (job.current) return;
      setPending({ action });
    }
    useImperativeHandle(ref, () => ({ guard }));
    const geometry = useMemo(() => inspection?.geometry ?? [], [inspection]);
    const layout = useMemo(
      () => readingLayout(geometry, dimensions.width, dimensions.height, zoom),
      [geometry, dimensions, zoom],
    );
    const priorLayout = useRef(layout);
    useLayoutEffect(() => {
      const node = viewport.current,
        old = priorLayout.current;
      priorLayout.current = layout;
      if (!node || !old.length || !layout.length) return;
      const anchor = readingPage(old, node.scrollTop + 24),
        fraction =
          (node.scrollTop - old[anchor]!.top) / (old[anchor]!.height + 48);
      node.scrollTop =
        layout[anchor]!.top + fraction * (layout[anchor]!.height + 48);
      setScrollTop(node.scrollTop);
    }, [layout]);
    const visible = readingWindow(layout, scrollTop, dimensions.height);
    const shape = useMemo(() => {
      if (!font || settings.type !== "text") return { value: null, error: "" };
      try {
        return { value: textShape(font, settings.text), error: "" };
      } catch (error) {
        return { value: null, error: (error as Error).message };
      }
    }, [font, settings.type, settings.text]);
    const planned = useMemo(() => {
      if (!inspection) return { value: null, error: "" };
      if (shape.error) return { value: null, error: shape.error };
      if (settings.type === "image" && !asset)
        return {
          value: null,
          error: "Choose a PNG or JPEG for your watermark.",
        };
      const ratio =
        settings.type === "text" && shape.value
          ? shape.value.width / shape.value.height
          : asset
            ? asset.width / asset.height
            : 0;
      try {
        return {
          value: planWatermarks(
            settings,
            geometry,
            ratio,
            inspection.annotations,
          ),
          error: "",
        };
      } catch (error) {
        return { value: null, error: (error as Error).message };
      }
    }, [settings, inspection, geometry, shape, asset]);
    const textPreview = useMemo(() => {
      const value = shape.value;
      if (!value || !/^#[\da-f]{6}$/i.test(settings.color)) return "";
      const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${value.width} ${value.height}"><g fill="${settings.color}" transform="translate(${-value.left} ${value.top}) scale(1 -1)">${value.paths.map((p) => `<path transform="translate(${p.x} 0)" d="${p.d}"/>`).join("")}</g></svg>`;
      return "data:image/svg+xml," + encodeURIComponent(svg);
    }, [shape, settings.color]);
    function update<K extends keyof WatermarkSettings>(
      key: K,
      value: WatermarkSettings[K],
    ) {
      setSettings((old) => ({ ...old, [key]: value }));
    }
    function go(next: number) {
      if (!Number.isInteger(next) || next < 0 || next >= geometry.length) {
        setPageError(`Choose a page from 1 to ${geometry.length}.`);
        return;
      }
      setPageError("");
      setPage(next);
      if (viewport.current) viewport.current.scrollTop = layout[next]!.top - 20;
      setScrollTop(viewport.current?.scrollTop ?? 0);
    }
    async function image(file: File) {
      if (job.current) return;
      const controller = new AbortController();
      job.current = controller;
      setBusy(true);
      setStage("Preparing your watermark image…");
      setFailure("");
      try {
        const next = await watermarkImage(file, controller.signal);
        if (controller.signal.aborted) {
          URL.revokeObjectURL(next.url);
          return;
        }
        setAsset(next);
      } catch (error) {
        setFailure(
          controller.signal.aborted
            ? "Cancelled. Your previous watermark and settings are unchanged."
            : (error as Error).message,
        );
      } finally {
        job.current = null;
        setBusy(false);
      }
    }
    async function submit() {
      if (job.current || !font || !planned.value) return;
      const controller = new AbortController();
      job.current = controller;
      setBusy(true);
      setFailure("");
      setStage("Preparing your watermarked PDF…");
      let timeout = false;
      const started = performance.now(),
        timer = setTimeout(() => {
          timeout = true;
          controller.abort();
        }, 120000);
      track("process_start", "watermark", {
        pages: planned.value.pages.length,
        totalBytes: props.file.size,
      });
      try {
        const result = await requestWatermark(
          props.file,
          controller.signal,
          settings,
          font,
          settings.type === "image" ? (asset ?? undefined) : undefined,
          setStage,
        );
        if (!(result instanceof Uint8Array) || controller.signal.aborted)
          throw Error("Cancelled");
        const retained = props.retainedFiles.reduce(
          (sum, file) => sum + file.size,
          0,
        );
        if (
          retained + result.byteLength + (asset?.bytes.length ?? 0) >
          PHOTO_LIMITS.sessionBytes
        )
          throw Error(
            "The result exceeds the task budget. Your original is unchanged.",
          );
        const output = new File(
          [result as Uint8Array<ArrayBuffer>],
          safeFilename(props.file.name.replace(/\.pdf$/i, "-watermarked.pdf")),
          { type: "application/pdf" },
        );
        if (!(await props.apply(output, props.pageIds, controller.signal)))
          throw Error(
            "The result could not be validated. Your PDF and watermark settings are unchanged.",
          );
        track("process_success", "watermark", {
          pages: planned.value.pages.length,
          totalBytes: output.size,
          durationMs: performance.now() - started,
        });
        props.onClose();
      } catch (error) {
        setFailure(
          timeout
            ? "Watermarking took too long. Choose fewer pages or a smaller PDF."
            : controller.signal.aborted
              ? "Cancelled. Your PDF and watermark settings are unchanged."
              : (error as Error).message,
        );
        track(
          controller.signal.aborted && !timeout
            ? "process_cancel"
            : "process_failure",
          "watermark",
          { reason: analyticsReason(error, timeout) },
        );
      } finally {
        clearTimeout(timer);
        job.current = null;
        setBusy(false);
      }
    }
    return (
      <section className="watermark-task" aria-label="Add watermark">
        <p className="source-context watermark-filename">{props.file.name}</p>
        <div className="watermark-workspace">
          <div className="watermark-preview">
            <div className="watermark-toolbar">
              <button
                className="secondary"
                aria-label="Previous page"
                disabled={busy || initialising || page === 0}
                onClick={() => go(page - 1)}
              >
                ←
              </button>
              <label>
                <span className="watermark-page-word">Page</span>{" "}
                <input
                  key={page}
                  aria-label="Preview page"
                  inputMode="numeric"
                  defaultValue={page + 1}
                  disabled={busy || !geometry.length}
                  onBlur={(event) => go(Number(event.target.value) - 1)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      go(Number(event.currentTarget.value) - 1);
                    }
                  }}
                />
                <span>/ {geometry.length || props.preview.doc.numPages}</span>
              </label>
              <button
                className="secondary"
                aria-label="Next page"
                disabled={busy || initialising || page >= geometry.length - 1}
                onClick={() => go(page + 1)}
              >
                →
              </button>
              <label className="watermark-zoom">
                <span className="sr-only">Zoom</span>
                <select
                  aria-label="Zoom"
                  value={zoom}
                  disabled={busy}
                  onChange={(event) => setZoom(Number(event.target.value))}
                >
                  <option value={-1}>Fit page</option>
                  <option value={1}>Fit width</option>
                  <option value={1.5}>150%</option>
                  <option value={2}>200%</option>
                </select>
              </label>
            </div>
            {pageError && (
              <p role="alert" className="watermark-error">
                {pageError}
              </p>
            )}
            <div
              className="watermark-viewport"
              ref={viewport}
              onScroll={(event) => {
                const top = event.currentTarget.scrollTop;
                setScrollTop(top);
                setPage(
                  readingPage(
                    layout,
                    top + Math.min(dimensions.height * 0.28, 200),
                  ),
                );
              }}
            >
              {initialising && (
                <p role="status" className="watermark-preview-status">
                  Preparing your PDF preview…
                </p>
              )}
              {initialError && (
                <div className="watermark-preview-status">
                  <p role="alert">{initialError}</p>
                  <button
                    className="secondary"
                    onClick={() => {
                      setInitialError("");
                      setInitialising(true);
                      setRetry((value) => value + 1);
                    }}
                  >
                    Retry preview
                  </button>
                </div>
              )}
              <div
                className="watermark-pages"
                style={{
                  height: layout.length
                    ? layout.at(-1)!.top + layout.at(-1)!.height + 24
                    : 200,
                  minWidth:
                    Math.max(dimensions.width, ...layout.map((p) => p.width)) +
                    40,
                }}
              >
                {layout.map((sheet, index) => {
                  const size = displaySize(geometry[index]!);
                  return (
                    <div
                      key={index}
                      className="watermark-sheet"
                      data-page={index + 1}
                      style={{
                        top: sheet.top,
                        width: sheet.width,
                        height: sheet.height,
                        left: Math.max(
                          20,
                          (dimensions.width + 40 - sheet.width) / 2,
                        ),
                      }}
                    >
                      <span className="watermark-page-label">
                        Page {index + 1}
                        {planned.value && !planned.value.pages.includes(index)
                          ? " · No watermark"
                          : ""}
                      </span>
                      <ContinuousCanvas
                        preview={props.preview}
                        index={index}
                        width={sheet.width}
                        height={sheet.height}
                        active={visible.has(index)}
                        ready={ready}
                      />
                      {visible.has(index) &&
                        readyPages.has(index) &&
                        planned.value?.stamps[index]!.map((stamp, n) => (
                          <img
                            key={n}
                            className="watermark-overlay"
                            alt=""
                            aria-hidden="true"
                            draggable={false}
                            src={
                              settings.type === "text"
                                ? textPreview
                                : asset?.url
                            }
                            style={{
                              left: (100 * stamp.cx) / size.width + "%",
                              top: (100 * stamp.cy) / size.height + "%",
                              width: (100 * stamp.width) / size.width + "%",
                              height: (100 * stamp.height) / size.height + "%",
                              opacity: settings.opacity / 100,
                              transform: `translate(-50%,-50%) rotate(${stamp.angle}deg)`,
                            }}
                          />
                        ))}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
          <aside className="watermark-settings">
            <fieldset disabled={busy || initialising}>
              <legend className="sr-only">Watermark settings</legend>
              <div
                className="watermark-segments"
                role="group"
                aria-label="Watermark type"
              >
                {(["text", "image"] as const).map((type) => (
                  <button
                    key={type}
                    className={settings.type === type ? "active" : "secondary"}
                    aria-pressed={settings.type === type}
                    onClick={() => update("type", type)}
                  >
                    {type === "text" ? "Text" : "Image"}
                  </button>
                ))}
              </div>
              {settings.type === "text" ? (
                <>
                  <label className="watermark-text">
                    Watermark text
                    <input
                      aria-label="Watermark text"
                      value={settings.text}
                      maxLength={240}
                      onChange={(event) => update("text", event.target.value)}
                    />
                  </label>
                  <label className="watermark-color">
                    Text color
                    <input
                      type="color"
                      aria-label="Text color"
                      value={settings.color}
                      onChange={(event) => update("color", event.target.value)}
                    />
                  </label>
                </>
              ) : (
                <div className="watermark-image-input">
                  <FilePicker
                    id="watermark-image"
                    accept=".png,.jpg,.jpeg,image/png,image/jpeg"
                    disabled={busy || initialising}
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      event.target.value = "";
                      if (file) void image(file);
                    }}
                  >
                    {asset ? "Replace image" : "Choose PNG or JPEG"}
                  </FilePicker>
                  <p>
                    {asset
                      ? `${asset.width} × ${asset.height} pixels`
                      : "Up to 5 MiB · 4 MP"}
                  </p>
                </div>
              )}
              <div
                className="watermark-segments"
                role="group"
                aria-label="Watermark layout"
              >
                {(["single", "repeat"] as const).map((mode) => (
                  <button
                    key={mode}
                    className={
                      settings.layout === mode ? "active" : "secondary"
                    }
                    aria-pressed={settings.layout === mode}
                    onClick={() => update("layout", mode)}
                  >
                    {mode === "single" ? "Single" : "Repeat"}
                  </button>
                ))}
              </div>
              {(
                [
                  ["size", "Size", 10, 80, "% of page width"],
                  ["opacity", "Opacity", 10, 100, "%"],
                  ["angle", "Rotation", -90, 90, "°"],
                ] as const
              ).map(([key, label, min, max, unit]) => (
                <label key={key} className="watermark-slider">
                  <span>
                    {label}
                    <output>
                      {settings[key]}
                      {unit}
                    </output>
                  </span>
                  <input
                    type="range"
                    aria-label={label}
                    min={min}
                    max={max}
                    step={1}
                    value={settings[key]}
                    onChange={(event) =>
                      update(key, Number(event.target.value))
                    }
                  />
                </label>
              ))}
              {settings.layout === "single" ? (
                <fieldset className="watermark-position">
                  <legend>Position</legend>
                  <div>
                    {positions.map((position, index) => (
                      <button
                        key={position}
                        className={
                          settings.position === index ? "active" : "secondary"
                        }
                        aria-label={position}
                        aria-pressed={settings.position === index}
                        onClick={() => update("position", index)}
                      >
                        <span aria-hidden="true">●</span>
                      </button>
                    ))}
                  </div>
                </fieldset>
              ) : (
                <label>
                  Repeat spacing
                  <select
                    aria-label="Repeat spacing"
                    value={settings.spacing}
                    onChange={(event) =>
                      update(
                        "spacing",
                        event.target.value as WatermarkSettings["spacing"],
                      )
                    }
                  >
                    <option value="tight">Tight</option>
                    <option value="normal">Normal</option>
                    <option value="wide">Wide</option>
                  </select>
                </label>
              )}
              <fieldset className="watermark-pages-choice">
                <legend>Pages</legend>
                <label>
                  <input
                    type="radio"
                    name="watermark-pages"
                    checked={settings.range === null}
                    onChange={() => update("range", null)}
                  />
                  All pages
                </label>
                <label>
                  <input
                    type="radio"
                    name="watermark-pages"
                    checked={settings.range !== null}
                    onChange={() => update("range", String(page + 1))}
                  />
                  Page range
                </label>
                {settings.range !== null && (
                  <input
                    aria-label="Page range"
                    placeholder="e.g. 1-3, 5"
                    value={settings.range}
                    onChange={(event) => update("range", event.target.value)}
                  />
                )}
              </fieldset>
            </fieldset>
            {planned.error && (
              <p className="watermark-error" role="alert">
                {planned.error}
              </p>
            )}
            {planned.value && (
              <p className="watermark-summary">
                {planned.value.count} watermark
                {planned.value.count === 1 ? "" : "s"} ·{" "}
                {planned.value.pages.length} page
                {planned.value.pages.length === 1 ? "" : "s"}
              </p>
            )}
            <div className="watermark-actions">
              <button
                disabled={busy || initialising || !planned.value}
                onClick={() => void submit()}
              >
                Add watermark →
              </button>
              <button
                className="secondary"
                onClick={() => {
                  if (initialising) {
                    job.current?.abort();
                    props.onClose();
                  } else guard(props.onClose);
                }}
                disabled={busy}
              >
                Cancel task
              </button>
            </div>
          </aside>
        </div>
        {pending && (
          <LeaveTaskDialog
            description="Your selected PDF and watermark settings will be cleared."
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
            message={stage}
            close={() => job.current?.abort()}
          />
        )}
        {!busy && failure && (
          <TaskNotice
            working={false}
            title="Your watermark was not added"
            message={failure}
            close={() => setFailure("")}
          />
        )}
      </section>
    );
  },
);
export { prepareWatermark } from "./font";
