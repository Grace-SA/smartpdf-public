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
import { glyphShape, glyphSvg } from "../overlay/text";
import { LeaveTaskDialog } from "../LeaveTaskDialog";
import { TaskNotice } from "../TaskNotice";
import { PHOTO_LIMITS, safeFilename } from "../photos/model";
import { track, analyticsReason } from "../analytics";
import { defaults, planNumbers, positions, type NumberSettings } from "./model";
import { prepareNumberFont } from "./font";
import { requestNumbers } from "./service";
import type { NumberInspection } from "./generate";
import "../watermark/watermark.css";
import "./numbers.css";

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
type Field = "from" | "to" | "start" | "size" | "margin";
function revealPreview(node: HTMLDivElement) {
  // In landscape the page field can be visible while its canvas is below the
  // screen. Reveal the preview frame as well as changing its internal scroll.
  node.parentElement?.scrollIntoView({ block: "nearest", inline: "nearest" });
}
export const NumberPanel = forwardRef<OrganizeHandle, Props>(
  function NumberPanel(props, ref) {
    const [settings, setSettings] = useState({
      ...defaults,
      to: props.preview.doc.numPages,
    });
    const [fields, setFields] = useState<Record<Field, string>>({
      from: "1",
      to: String(props.preview.doc.numPages),
      start: "1",
      size: "12",
      margin: "10",
    });
    const [inspection, setInspection] = useState<NumberInspection | null>(null),
      [font, setFont] = useState<Uint8Array | null>(null);
    const [initialising, setInitialising] = useState(true),
      [initialError, setInitialError] = useState(""),
      [retry, setRetry] = useState(0);
    const [busy, setBusy] = useState(false),
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
    const { onDirty, onBusy } = props;
    useEffect(() => {
      onDirty(true);
      return () => onDirty(false);
    }, [onDirty]);
    useEffect(() => {
      onBusy(initialising || busy);
      return () => onBusy(false);
    }, [initialising, busy, onBusy]);
    useEffect(() => () => job.current?.abort(), []);
    useEffect(() => {
      const controller = new AbortController();
      job.current = controller;
      void Promise.all([
        requestNumbers(props.file, controller.signal),
        prepareNumberFont(controller.signal),
      ])
        .then(([result, bytes]) => {
          if (controller.signal.aborted) return;
          if (result instanceof Uint8Array)
            throw Error("Page inspection could not finish.");
          setInspection(result);
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
    const geometry = inspection?.geometry;
    const layout = useMemo(
      () =>
        readingLayout(
          geometry ?? [],
          dimensions.width,
          dimensions.height,
          zoom,
        ),
      [geometry, dimensions, zoom],
    );
    const priorLayout = useRef(layout);
    // Keep an explicit jump authoritative while ResizeObserver catches up.
    // Natural scrolling releases it; programmatic scroll events must not.
    const requestedPage = useRef<number | null>(null);
    useLayoutEffect(() => {
      const node = viewport.current,
        old = priorLayout.current;
      priorLayout.current = layout;
      if (!node || !old.length || !layout.length) return;
      if (requestedPage.current !== null && layout[requestedPage.current]) {
        node.scrollTop = layout[requestedPage.current]!.top - 20;
        revealPreview(node);
        setScrollTop(node.scrollTop);
        setPage(requestedPage.current);
        return;
      }
      const anchor = readingPage(old, node.scrollTop + 24),
        fraction =
          (node.scrollTop - old[anchor]!.top) / (old[anchor]!.height + 48);
      node.scrollTop =
        layout[anchor]!.top + fraction * (layout[anchor]!.height + 48);
      setScrollTop(node.scrollTop);
    }, [layout]);
    const visible = readingWindow(layout, scrollTop, dimensions.height);
    const effective = useMemo<NumberSettings>(
      () => ({
        ...settings,
        from: Number(fields.from),
        to: Number(fields.to),
        start: Number(fields.start),
        size: Number(fields.size),
        margin: Number(fields.margin),
      }),
      [settings, fields],
    );
    const planned = useMemo(() => {
      if (!inspection || !font) return { value: null, error: "" };
      try {
        return {
          value: planNumbers(
            effective,
            inspection.geometry,
            (text) => glyphShape(font, text),
            inspection.annotations,
          ),
          error: "",
        };
      } catch (error) {
        return { value: null, error: (error as Error).message };
      }
    }, [inspection, font, effective]);
    function update<K extends keyof NumberSettings>(
      key: K,
      value: NumberSettings[K],
    ) {
      setSettings((old) => ({ ...old, [key]: value }));
    }
    function field(key: Field, value: string) {
      setFields((old) => ({ ...old, [key]: value }));
    }
    function go(next: number) {
      const count = props.preview.doc.numPages;
      if (!Number.isInteger(next) || next < 0 || next >= count) {
        setPageError(`Choose a page from 1 to ${count}.`);
        return;
      }
      setPageError("");
      requestedPage.current = next;
      setPage(next);
      if (viewport.current && layout[next]) {
        viewport.current.scrollTop = layout[next]!.top - 20;
        revealPreview(viewport.current);
      }
      setScrollTop(viewport.current?.scrollTop ?? 0);
    }
    function guard(action: () => void) {
      if (job.current) return;
      setPending({ action });
    }
    useImperativeHandle(ref, () => ({ guard }));
    async function submit() {
      if (job.current || !font || !planned.value) return;
      const controller = new AbortController();
      job.current = controller;
      setBusy(true);
      setFailure("");
      setStage("Preparing your numbered PDF…");
      const started = performance.now();
      track("process_start", "numbers", {
        pages: planned.value.pages.length,
        totalBytes: props.file.size,
      });
      try {
        const result = await requestNumbers(
          props.file,
          controller.signal,
          effective,
          font,
          setStage,
        );
        if (!(result instanceof Uint8Array) || controller.signal.aborted)
          throw Error("Cancelled");
        if (
          props.retainedFiles.reduce((sum, file) => sum + file.size, 0) +
            result.length >
          PHOTO_LIMITS.sessionBytes
        )
          throw Error(
            "The result exceeds the task budget. Your original is unchanged.",
          );
        const output = new File(
          [result as Uint8Array<ArrayBuffer>],
          safeFilename(props.file.name.replace(/\.pdf$/i, "-numbered.pdf")),
          { type: "application/pdf" },
        );
        if (!(await props.apply(output, props.pageIds, controller.signal)))
          throw Error(
            "The numbered PDF could not be validated. Your settings are unchanged.",
          );
        track("process_success", "numbers", {
          pages: planned.value.pages.length,
          totalBytes: output.size,
          durationMs: performance.now() - started,
        });
        props.onClose();
      } catch (error) {
        setFailure(
          controller.signal.aborted
            ? "Cancelled. Your PDF and number settings are unchanged."
            : (error as Error).message,
        );
        track(
          controller.signal.aborted ? "process_cancel" : "process_failure",
          "numbers",
          { reason: analyticsReason(error) },
        );
      } finally {
        job.current = null;
        setBusy(false);
      }
    }
    return (
      <section
        className="numbers-task watermark-task"
        aria-label="Add page numbers"
      >
        <h2 className="watermark-filename">{props.file.name}</h2>
        <div className="watermark-workspace">
          <div className="watermark-preview">
            <div
              className="watermark-toolbar"
              role="group"
              aria-label="Page preview navigation"
            >
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
                  disabled={busy || initialising}
                  onBlur={(e) => go(Number(e.target.value) - 1)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      go(Number(e.currentTarget.value) - 1);
                    }
                  }}
                />
                <span>/ {props.preview.doc.numPages}</span>
              </label>
              <button
                className="secondary"
                aria-label="Next page"
                disabled={
                  busy || initialising || page >= props.preview.doc.numPages - 1
                }
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
                  onChange={(e) => setZoom(Number(e.target.value))}
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
              tabIndex={0}
              aria-label="PDF page preview"
              onWheel={() => {
                requestedPage.current = null;
              }}
              onTouchStart={() => {
                requestedPage.current = null;
              }}
              onPointerDown={() => {
                requestedPage.current = null;
              }}
              onKeyDown={() => {
                requestedPage.current = null;
              }}
              onScroll={(e) => {
                const top = e.currentTarget.scrollTop;
                setScrollTop(top);
                setPage(
                  requestedPage.current ??
                    readingPage(
                      layout,
                      top + Math.min(dimensions.height * 0.28, 200),
                    ),
                );
              }}
            >
              {initialising && (
                <p role="status" className="watermark-preview-status">
                  Preparing your pages…
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
                      setRetry((v) => v + 1);
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
                  const size = displaySize(geometry![index]!),
                    stamp = planned.value?.stamps[index];
                  return (
                    <div
                      key={index}
                      className="watermark-sheet number-sheet"
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
                        PDF page {index + 1}
                        {planned.value
                          ? stamp
                            ? ` · ${stamp.text}`
                            : " · No added number"
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
                      {visible.has(index) && readyPages.has(index) && stamp && (
                        <img
                          className="watermark-overlay number-overlay"
                          alt=""
                          aria-hidden="true"
                          draggable={false}
                          src={glyphSvg(stamp.shape, effective.color)}
                          style={{
                            left:
                              ((stamp.x + stamp.width / 2) / size.width) * 100 +
                              "%",
                            top:
                              ((stamp.y + stamp.height / 2) / size.height) *
                                100 +
                              "%",
                            width: (stamp.width / size.width) * 100 + "%",
                            height: (stamp.height / size.height) * 100 + "%",
                            transform: "translate(-50%,-50%)",
                          }}
                        />
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
          <aside className="watermark-settings number-settings">
            <fieldset disabled={busy || initialising}>
              <legend className="sr-only">Page number settings</legend>
              <fieldset className="number-position">
                <legend>Position</legend>
                <div>
                  {positions.map((label, index) => (
                    <button
                      key={label}
                      className={
                        settings.position === index ? "active" : "secondary"
                      }
                      aria-label={label}
                      aria-pressed={settings.position === index}
                      onClick={() => update("position", index)}
                    >
                      <span
                        className="number-position-paper"
                        aria-hidden="true"
                      >
                        <b
                          style={{
                            left: ["18%", "50%", "82%"][index % 3],
                            top: index < 3 ? "22%" : "78%",
                          }}
                        >
                          1
                        </b>
                      </span>
                      <span>{label}</span>
                    </button>
                  ))}
                </div>
              </fieldset>
              <label className="number-control">
                Format
                <select
                  aria-label="Number format"
                  value={settings.format}
                  onChange={(e) =>
                    update("format", e.target.value as NumberSettings["format"])
                  }
                >
                  <option value="number">1</option>
                  <option value="fraction">1 / 10</option>
                  <option value="page-total">Page 1 of 10</option>
                </select>
              </label>
              {settings.format !== "number" && (
                <p className="number-hint">Total follows the last number.</p>
              )}
              <fieldset className="number-pages">
                <legend>Pages to number</legend>
                {(
                  [
                    ["all", "All pages"],
                    ["skip-first", "Skip first page"],
                    ["range", "Page range"],
                  ] as const
                ).map(([value, label]) => (
                  <label key={value}>
                    <input
                      type="radio"
                      name="number-pages"
                      checked={settings.mode === value}
                      onChange={() => update("mode", value)}
                    />
                    {label}
                  </label>
                ))}
              </fieldset>
              {settings.mode === "range" && (
                <div className="number-range">
                  <label>
                    From PDF page
                    <input
                      aria-label="From PDF page"
                      inputMode="numeric"
                      value={fields.from}
                      onChange={(e) => field("from", e.target.value)}
                    />
                  </label>
                  <label>
                    To PDF page
                    <input
                      aria-label="To PDF page"
                      inputMode="numeric"
                      value={fields.to}
                      onChange={(e) => field("to", e.target.value)}
                    />
                  </label>
                </div>
              )}
              <label className="number-control">
                Start number
                <input
                  aria-label="Start number"
                  inputMode="numeric"
                  value={fields.start}
                  onChange={(e) => field("start", e.target.value)}
                />
              </label>
              <details className="number-appearance">
                <summary>Appearance</summary>
                <label>
                  Font size (pt)
                  <input
                    aria-label="Font size (pt)"
                    inputMode="decimal"
                    value={fields.size}
                    onChange={(e) => field("size", e.target.value)}
                  />
                </label>
                <label>
                  Margin (mm)
                  <input
                    aria-label="Margin (mm)"
                    inputMode="decimal"
                    value={fields.margin}
                    onChange={(e) => field("margin", e.target.value)}
                  />
                </label>
                <label className="watermark-color">
                  Number color
                  <input
                    type="color"
                    aria-label="Number color"
                    value={settings.color}
                    onChange={(e) => update("color", e.target.value)}
                  />
                </label>
              </details>
            </fieldset>
            {planned.error && (
              <p role="alert" className="watermark-error">
                {planned.error}
              </p>
            )}
            {planned.value && (
              <p className="number-summary">
                {planned.value.pages.length} page
                {planned.value.pages.length === 1 ? "" : "s"} · PDF{" "}
                {planned.value.pages[0]! + 1}–{planned.value.pages.at(-1)! + 1}
                <br />
                Numbers {planned.value.first}–{planned.value.last}
              </p>
            )}
            <p className="number-hint">
              Existing page numbers are not removed. Check your position in the
              preview.
            </p>
            <div className="watermark-actions number-actions">
              <button
                disabled={busy || initialising || !planned.value}
                onClick={() => void submit()}
              >
                Add page numbers →
              </button>
              <button
                className="secondary"
                disabled={busy}
                onClick={() => {
                  if (initialising) {
                    job.current?.abort();
                    props.onClose();
                  } else guard(props.onClose);
                }}
              >
                Cancel task
              </button>
            </div>
          </aside>
        </div>
        {pending && (
          <LeaveTaskDialog
            description="Your selected PDF and page number settings will be cleared."
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
            title="Your page numbers were not added"
            message={failure}
            close={() => setFailure("")}
          />
        )}
      </section>
    );
  },
);
export { prepareNumberFont } from "./font";
