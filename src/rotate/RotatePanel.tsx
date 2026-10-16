import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import type { RenderTask } from "pdfjs-dist/legacy/build/pdf.mjs";
import type { Preview } from "../platform/engine";
import type { OrganizeHandle } from "../organize/OrganizePanel";
import { PageDetail } from "../organize/PageDetail";
import { pageRange } from "../organize/range";
import { LIMITS } from "../core/contracts";
import { PHOTO_LIMITS, safeFilename } from "../photos/model";
import { LeaveTaskDialog } from "../LeaveTaskDialog";
import { TaskNotice } from "../TaskNotice";
import { analyticsReason, track } from "../analytics";
import { turnPages } from "./model";
import { processRotations } from "./service";
import "./rotate.css";

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
const ROW = 236;

function Thumbnail({
  preview,
  index,
  turns,
}: {
  preview: Preview;
  index: number;
  turns: number;
}) {
  const host = useRef<HTMLSpanElement>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let stopped = false,
      render: RenderTask | undefined;
    const canvas = document.createElement("canvas");
    let page: Awaited<ReturnType<Preview["doc"]["getPage"]>> | undefined;
    void (async () => {
      try {
        page = await preview.doc.getPage(index + 1);
        if (stopped) return;
        const base = page.getViewport({ scale: 1 });
        const viewport = page.getViewport({
          scale: Math.min(142 / base.width, 142 / base.height),
        });
        canvas.width = Math.max(1, Math.ceil(viewport.width));
        canvas.height = Math.max(1, Math.ceil(viewport.height));
        canvas.setAttribute("aria-hidden", "true");
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
    <span className="rotate-thumbnail">
      <span ref={host} style={{ transform: `rotate(${turns * 90}deg)` }} />
      {failed && <small>Preview unavailable</small>}
    </span>
  );
}

export const RotatePanel = forwardRef<OrganizeHandle, Props>(
  function RotatePanel(props, ref) {
    const [turns, setTurns] = useState(() => props.pageIds.map(() => 0));
    const [past, setPast] = useState<number[][]>([]),
      [future, setFuture] = useState<number[][]>([]);
    const [scope, setScope] = useState("all"),
      [selected, setSelected] = useState<Set<number>>(() => new Set());
    const [range, setRange] = useState(""),
      [rangeError, setRangeError] = useState("");
    const [detail, setDetail] = useState<number | null>(null);
    const [top, setTop] = useState(0),
      [columns, setColumns] = useState(2);
    const [busy, setBusy] = useState(false),
      [failure, setFailure] = useState("");
    const [pending, setPending] = useState<{ action: () => void } | null>(null);
    const task = useRef<AbortController | null>(null),
      host = useRef<HTMLDivElement>(null);
    const changed = turns.filter(Boolean).length;
    const { onDirty, onBusy } = props;
    useEffect(() => {
      onDirty(changed > 0);
    }, [changed, onDirty]);
    useEffect(() => {
      onBusy(busy);
    }, [busy, onBusy]);
    useEffect(
      () => () => {
        task.current?.abort();
        onDirty(false);
        onBusy(false);
      },
      [onDirty, onBusy],
    );
    function guard(action: () => void) {
      if (task.current) return;
      if (changed) setPending({ action });
      else action();
    }
    useImperativeHandle(ref, () => ({ guard }));
    useEffect(() => {
      const element = host.current;
      if (!element) return;
      const observer = new ResizeObserver(([entry]) =>
        setColumns(
          Math.max(
            2,
            Math.min(5, Math.floor((entry?.contentRect.width ?? 340) / 170)),
          ),
        ),
      );
      observer.observe(element);
      return () => observer.disconnect();
    }, []);
    function change(next: number[]) {
      if (task.current || next.every((turn, i) => turn === turns[i])) return;
      setPast((old) => [...old, turns].slice(-100));
      setFuture([]);
      setTurns(next);
    }
    function travel(redo: boolean) {
      if (task.current) return;
      const from = redo ? future : past,
        target = from.at(-1);
      if (!target) return;
      if (redo) {
        setFuture(from.slice(0, -1));
        setPast((old) => [...old, turns].slice(-100));
      } else {
        setPast(from.slice(0, -1));
        setFuture((old) => [...old, turns].slice(-100));
      }
      setTurns(target);
    }
    const positions = scope === "all" ? turns.map((_, i) => i) : [...selected];
    const start = Math.max(0, Math.floor(top / ROW) - 2) * columns;
    const visible = turns.slice(start, start + 8 * columns);
    async function apply() {
      if (task.current || !changed) return;
      const controller = new AbortController();
      task.current = controller;
      setBusy(true);
      setFailure("");
      const started = performance.now();
      let timeout = false;
      const timer = setTimeout(() => {
        timeout = true;
        controller.abort();
      }, LIMITS.timeoutMs);
      track("process_start", "rotate", {
        fileCount: 1,
        pages: turns.length,
        totalBytes: props.file.size,
      });
      try {
        const bytes = await processRotations(
          props.file,
          turns,
          controller.signal,
        );
        const retained = [...new Set(props.retainedFiles)].reduce(
          (sum, file) => sum + file.size,
          0,
        );
        if (retained + bytes.byteLength > PHOTO_LIMITS.sessionBytes)
          throw new Error(
            "This result exceeds the task budget. Your original is unchanged.",
          );
        const file = new File(
          [bytes as Uint8Array<ArrayBuffer>],
          safeFilename(props.file.name.replace(/\.pdf$/i, "-rotated.pdf")),
          { type: "application/pdf" },
        );
        if (
          controller.signal.aborted ||
          !(await props.apply(file, props.pageIds, controller.signal))
        )
          throw new Error(
            "The rotated PDF could not be validated. Your original and draft are unchanged.",
          );
        track("process_success", "rotate", {
          fileCount: 1,
          pages: turns.length,
          totalBytes: file.size,
          durationMs: performance.now() - started,
        });
        props.onClose();
      } catch (error) {
        track(
          controller.signal.aborted && !timeout
            ? "process_cancel"
            : "process_failure",
          "rotate",
          {
            durationMs: performance.now() - started,
            reason: analyticsReason(error, timeout),
          },
        );
        setFailure(
          timeout
            ? "Rotating took too long. Your original and draft are unchanged. Try a smaller PDF."
            : controller.signal.aborted
              ? "Cancelled. Your original and rotation draft are unchanged."
              : error instanceof Error
                ? error.message
                : "Rotation failed. Your original and draft are unchanged.",
        );
      } finally {
        clearTimeout(timer);
        task.current = null;
        setBusy(false);
      }
    }
    return (
      <section className="rotate-task" aria-label="Rotate pages">
        <div className="rotate-topbar">
          <p className="source-context">{props.file.name}</p>
          <div className="workspace-toolbar">
            <span>{turns.length} pages</span>
            <button
              className="secondary"
              disabled={busy || !past.length}
              aria-label="Undo rotation"
              onClick={() => travel(false)}
            >
              ↶ Undo
            </button>
            <button
              className="secondary"
              disabled={busy || !future.length}
              aria-label="Redo rotation"
              onClick={() => travel(true)}
            >
              ↷ Redo
            </button>
            <button
              className="secondary"
              disabled={busy || !changed}
              aria-label="Reset rotations"
              onClick={() => change(turns.map(() => 0))}
            >
              Reset
            </button>
          </div>
        </div>
        <div className="rotate-layout">
          <div
            ref={host}
            className="rotate-viewport"
            tabIndex={0}
            role="region"
            aria-label="PDF page thumbnails"
            onScroll={(event) => setTop(event.currentTarget.scrollTop)}
          >
            <div
              style={{
                height: Math.ceil(turns.length / columns) * ROW,
                position: "relative",
              }}
            >
              {visible.map((turn, offset) => {
                const index = start + offset;
                return (
                  <div
                    key={props.pageIds[index]}
                    className="rotate-card"
                    data-page={index + 1}
                    data-turns={turn}
                    data-selected={scope === "selected" && selected.has(index)}
                    style={{
                      position: "absolute",
                      top: Math.floor(index / columns) * ROW,
                      left: `${((index % columns) * 100) / columns}%`,
                      width: `${100 / columns}%`,
                      height: ROW,
                    }}
                  >
                    <button
                      className="rotate-face"
                      disabled={busy}
                      aria-label={`Enlarge page ${index + 1}`}
                      onClick={() => setDetail(index)}
                    >
                      <Thumbnail
                        preview={props.preview}
                        index={index}
                        turns={turn}
                      />
                      <span>
                        Page {index + 1}
                        {turn ? " · Rotated" : ""}
                      </span>
                    </button>
                    <div className="rotate-card-actions">
                      {scope === "selected" && (
                        <label>
                          <input
                            type="checkbox"
                            disabled={busy}
                            aria-label={`Select page ${index + 1}`}
                            checked={selected.has(index)}
                            onChange={() =>
                              setSelected((old) => {
                                const next = new Set(old);
                                if (next.has(index)) next.delete(index);
                                else next.add(index);
                                return next;
                              })
                            }
                          />{" "}
                          Select
                        </label>
                      )}
                      <button
                        className="secondary"
                        disabled={busy}
                        aria-label={`Rotate page ${index + 1} right`}
                        title="Rotate 90° right"
                        onClick={() => change(turnPages(turns, [index], 1))}
                      >
                        ↻
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
          <div className="rotate-settings">
            <h2>Rotate your pages</h2>
            <p>Tap a page to enlarge. Use ↻ to turn one page.</p>
            <fieldset disabled={busy}>
              <legend>Batch rotation</legend>
              <label>
                Apply to
                <select
                  aria-label="Apply to"
                  value={scope}
                  onChange={(event) => setScope(event.target.value)}
                >
                  <option value="all">All pages</option>
                  <option value="selected">Selected pages</option>
                </select>
              </label>
              {scope === "selected" && (
                <>
                  <p className="rotate-selection-status" role="status">
                    {selected.size} of {turns.length} pages selected
                  </p>
                  <details>
                    <summary>Select a page range</summary>
                    <label>
                      Page numbers
                      <input
                        value={range}
                        placeholder="1-3, 5"
                        maxLength={2000}
                        onChange={(event) => setRange(event.target.value)}
                      />
                    </label>
                    <button
                      className="secondary"
                      onClick={() => {
                        try {
                          const indices = pageRange(range, turns.length);
                          setSelected(new Set(indices));
                          setRangeError("");
                          if (host.current)
                            host.current.scrollTop =
                              Math.floor(indices[0]! / columns) * ROW;
                        } catch (error) {
                          setRangeError((error as Error).message);
                        }
                      }}
                    >
                      Select range
                    </button>
                    {rangeError && <p role="alert">{rangeError}</p>}
                  </details>
                </>
              )}
              <div className="rotate-directions">
                <button
                  className="secondary"
                  disabled={busy || !positions.length}
                  onClick={() => change(turnPages(turns, positions, -1))}
                >
                  ↶ Rotate left
                </button>
                <button
                  className="secondary"
                  disabled={busy || !positions.length}
                  onClick={() => change(turnPages(turns, positions, 1))}
                >
                  ↻ Rotate right
                </button>
              </div>
            </fieldset>
            <p className="rotate-summary" role="status">
              {changed
                ? `${changed} of ${turns.length} pages changed`
                : "Rotate a page to create your PDF."}
            </p>
            <div className="rotate-submit">
              <button disabled={busy || !changed} onClick={() => void apply()}>
                Create PDF →
              </button>
              <button
                className="secondary"
                disabled={busy}
                onClick={() => guard(props.onClose)}
              >
                Cancel task
              </button>
            </div>
          </div>
        </div>
        {detail !== null && (
          <PageDetail
            preview={props.preview}
            title="Rotation preview"
            initialIndex={detail}
            entries={props.pageIds.map((id, source) => ({
              id,
              source,
              turns: turns[source]!,
              position: source + 1,
            }))}
            close={() => setDetail(null)}
          />
        )}
        {(busy || failure) && (
          <TaskNotice
            working={busy}
            message={busy ? "Rotating and checking your PDF…" : failure}
            close={() => {
              if (task.current) task.current.abort();
              else setFailure("");
            }}
          />
        )}
        {pending && (
          <LeaveTaskDialog
            description="Your page rotation changes will be discarded."
            keep={() => setPending(null)}
            leave={() => {
              const action = pending.action;
              setPending(null);
              action();
            }}
          />
        )}
      </section>
    );
  },
);
