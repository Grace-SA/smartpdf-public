import { LeaveTaskDialog } from "../LeaveTaskDialog";
import { TaskNotice } from "../TaskNotice";
import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import type { RenderTask } from "pdfjs-dist/legacy/build/pdf.mjs";
import type { Preview } from "../platform/engine";
import { LIMITS } from "../core/contracts";
import { PHOTO_LIMITS, safeFilename } from "../photos/model";
import { movePages, placePages, type PageEntry } from "./model";
import { processPages } from "./service";
import { analyticsReason, track } from "../analytics";
import { pageRange } from "./range";
import { CardMove } from "../CardMove";
import { PageDetail } from "./PageDetail";
export type OrganizeHandle = { guard: (action: () => void) => void };
type Props = {
  file: File;
  preview: Preview;
  pageIds: string[];
  retainedFiles: File[];
  apply: (file: File, ids: string[], signal: AbortSignal) => Promise<boolean>;
  onClose: () => void;
  onDirty: (v: boolean) => void;
  onBusy: (v: boolean) => void;
};
const ROW = 230,
  WINDOW = 4,
  OVERSCAN = 2;
export const OrganizePanel = forwardRef<OrganizeHandle, Props>(
  function OrganizePanel(props, ref) {
    const initial = useMemo(
      () => props.pageIds.map((id, source) => ({ id, source, turns: 0 })),
      [props.pageIds],
    );
    const [pages, setPages] = useState<PageEntry[]>(initial),
      [selected, setSelected] = useState<Set<string>>(() => new Set());
    type Snapshot = { pages: PageEntry[]; selected: Set<string> };
    const [past, setPast] = useState<Snapshot[]>([]),
      [future, setFuture] = useState<Snapshot[]>([]);
    const [adjustAssociations, setAdjustAssociations] = useState(false);
    const [selecting, setSelecting] = useState(false);
    const [range, setRange] = useState("");
    const [detailStart, setDetailStart] = useState(0);
    const [detail, setDetail] = useState<
      (PageEntry & { position: number })[] | null
    >(null);
    const [top, setTop] = useState(0),
      [position, setPosition] = useState(1),
      [message, setMessage] = useState(""),
      [busy, setBusy] = useState(false);
    const [failure, setFailure] = useState("");
    const [pending, setPending] = useState<{ action: () => void } | null>(null);
    const task = useRef<AbortController | null>(null),
      host = useRef<HTMLDivElement>(null);
    const dirty =
      pages.length !== initial.length ||
      pages.some((p, i) => p.id !== initial[i]?.id || p.turns !== 0);
    const { onDirty, onBusy } = props;
    useEffect(() => {
      onDirty(dirty);
    }, [dirty, onDirty]);
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
      if (dirty) setPending({ action });
      else action();
    }
    useImperativeHandle(ref, () => ({ guard }));
    const [columns, setColumns] = useState(2);
    useEffect(() => {
      if (!host.current) return;
      const observer = new ResizeObserver(([entry]) => {
        setColumns(
          Math.max(
            2,
            Math.min(5, Math.floor((entry?.contentRect.width ?? 340) / 170)),
          ),
        );
      });
      observer.observe(host.current);
      return () => observer.disconnect();
    }, []);
    const start =
      Math.max(
        0,
        Math.min(Math.ceil(pages.length / columns) - 1, Math.floor(top / ROW)) -
          OVERSCAN,
      ) * columns;
    const visible = useMemo(
      () => pages.slice(start, start + (WINDOW + OVERSCAN * 2) * columns),
      [pages, start, columns],
    );
    useEffect(() => {
      let stopped = false,
        render: RenderTask | undefined;
      const root = host.current;
      const canvases: HTMLCanvasElement[] = [];
      void (async () => {
        for (const entry of visible) {
          if (stopped) break;
          const holder = [
            ...(root?.querySelectorAll<HTMLElement>("[data-thumbnail]") ?? []),
          ].find((e) => e.dataset.thumbnail === entry.id);
          if (!holder) continue;
          let page;
          try {
            page = await props.preview.doc.getPage(entry.source + 1);
            if (stopped) break;
            const base = page.getViewport({
              scale: 1,
              rotation: (page.rotate + entry.turns * 90) % 360,
            });
            const viewport = page.getViewport({
              scale: Math.min(140 / base.width, 156 / base.height),
              rotation: (page.rotate + entry.turns * 90) % 360,
            });
            const canvas = document.createElement("canvas");
            canvases.push(canvas);
            canvas.width = Math.max(1, Math.floor(viewport.width));
            canvas.height = Math.max(1, Math.floor(viewport.height));
            canvas.setAttribute("aria-hidden", "true");
            render = page.render({
              canvas,
              canvasContext: canvas.getContext("2d")!,
              viewport,
              annotationMode: 1,
            });
            await render.promise;
            if (!stopped) holder.replaceChildren(canvas);
          } catch {
            if (!stopped) holder.textContent = "Thumbnail unavailable";
          } finally {
            page?.cleanup();
          }
        }
      })();
      return () => {
        stopped = true;
        render?.cancel();
        for (const c of canvases) {
          c.width = c.height = 0;
          c.remove();
        }
      };
    }, [visible, props.preview]);
    useEffect(() => {
      if (window.matchMedia("(max-width: 640px)").matches)
        host.current
          ?.closest(".organize-task")
          ?.scrollIntoView({ block: "start" });
    }, []);
    function change(next: PageEntry[]) {
      if (task.current) return;
      if (
        next.length === pages.length &&
        next.every(
          (p, i) => p.id === pages[i]?.id && p.turns === pages[i]?.turns,
        )
      )
        return;
      setPast((old) =>
        [...old, { pages, selected: new Set(selected) }].slice(-100),
      );
      setFuture([]);
      setAdjustAssociations(false);
      setPages(next);
      setMessage("");
    }
    function travel(redo: boolean) {
      if (task.current) return;
      const from = redo ? future : past,
        target = from.at(-1);
      if (!target) return;
      const current = { pages, selected: new Set(selected) };
      if (redo) {
        setFuture(from.slice(0, -1));
        setPast((old) => [...old, current].slice(-100));
      } else {
        setPast(from.slice(0, -1));
        setFuture((old) => [...old, current].slice(-100));
      }
      setPages(target.pages);
      setSelected(selecting ? new Set(target.selected) : new Set());
      setAdjustAssociations(false);
      setMessage("");
    }
    function remove(ids = selected) {
      if (task.current) return;
      if (ids.size >= pages.length) {
        setMessage("Keep at least one page. No pages were deleted.");
        return;
      }
      change(pages.filter((p) => !ids.has(p.id)));
      setSelected(new Set());
    }
    async function apply(allowAdjustment = adjustAssociations) {
      if (task.current || !dirty) return false;
      const started = performance.now();
      track("process_start", "organize", {
        fileCount: 1,
        totalBytes: props.file.size,
        pages: pages.length,
      });
      const controller = new AbortController();
      task.current = controller;
      setBusy(true);
      setMessage("");
      setFailure("");
      let timeout = false;
      const timer = setTimeout(() => {
        timeout = true;
        controller.abort();
      }, LIMITS.timeoutMs);
      try {
        const bytes = await processPages(
          props.file,
          pages,
          controller.signal,
          allowAdjustment,
        );
        const retained = [...new Set(props.retainedFiles)].reduce(
          (n, f) => n + f.size,
          0,
        );
        if (retained + bytes.byteLength > PHOTO_LIMITS.sessionBytes)
          throw new Error(
            "This change exceeds the task budget. Your source is unchanged.",
          );
        const file = new File(
          [bytes as Uint8Array<ArrayBuffer>],
          safeFilename(props.file.name.replace(/\.pdf$/i, "-organized.pdf")),
          { type: "application/pdf" },
        );
        if (
          !(await props.apply(
            file,
            pages.map((p) => p.id),
            controller.signal,
          ))
        )
          throw new Error(
            "The result could not be previewed. Your previous document is unchanged.",
          );
        track("process_success", "organize", {
          fileCount: 1,
          totalBytes: file.size,
          pages: pages.length,
          durationMs: performance.now() - started,
        });
        return true;
      } catch (error) {
        track(
          controller.signal.aborted && !timeout
            ? "process_cancel"
            : "process_failure",
          "organize",
          {
            durationMs: performance.now() - started,
            reason: analyticsReason(error, timeout),
          },
        );
        setFailure(
          timeout
            ? "Organizing took too long. Your previous document is unchanged."
            : controller.signal.aborted
              ? "Cancelled. Your previous document and draft are unchanged."
              : error instanceof Error
                ? error.message
                : "Organizing failed.",
        );
        return false;
      } finally {
        clearTimeout(timer);
        task.current = null;
        setBusy(false);
      }
    }
    return (
      <section
        className="organize-task direct-workspace"
        data-has-selection={selected.size > 0}
        aria-label="Organize pages"
      >
        <p className="source-context">{props.file.name}</p>
        <div className="workspace-toolbar">
          <span role="status">
            {pages.length} pages
            {selecting ? ` · ${selected.size} selected` : ""}
          </span>
          <button
            className="secondary"
            disabled={busy || !past.length}
            aria-label="Undo draft change"
            onClick={() => travel(false)}
          >
            ↶ Undo
          </button>
          <button
            className="secondary"
            disabled={busy || !future.length}
            aria-label="Redo draft change"
            onClick={() => travel(true)}
          >
            ↷ Redo
          </button>
          <button
            className="secondary"
            disabled={busy}
            aria-pressed={selecting}
            onClick={() => {
              setSelecting(!selecting);
              setSelected(new Set());
            }}
          >
            {selecting ? "Done selecting" : "Select pages"}
          </button>
        </div>
        <p className="workspace-hint">
          {selecting
            ? "Tap pages to select them, then choose an action."
            : "Tap a page to enlarge. Drag its handle to reorder, or tap the handle to choose a position."}
        </p>
        <fieldset disabled={busy}>
          <legend>Page selection and changes</legend>
          {selecting && (
            <div className="batch-controls">
              <details className="organize-range">
                <summary>Select a page range</summary>
                <label>
                  Current page positions
                  <input
                    value={range}
                    maxLength={2000}
                    placeholder="3-8, 12"
                    onChange={(e) => setRange(e.target.value)}
                  />
                </label>
                <p>
                  Use current positions, not original page numbers. This
                  replaces the selection.
                </p>
                <button
                  onClick={() => {
                    if (task.current) return;
                    try {
                      const positions = pageRange(range, pages.length);
                      setSelected(new Set(positions.map((i) => pages[i]!.id)));
                      setMessage(
                        `Selected ${positions.length} pages by current position.`,
                      );
                      if (host.current)
                        host.current.scrollTop =
                          Math.floor(positions[0]! / columns) * ROW;
                    } catch (error) {
                      setMessage((error as Error).message);
                    }
                  }}
                >
                  Select range
                </button>
              </details>
              <button
                className="secondary"
                disabled={!selected.size}
                onClick={() => {
                  if (!task.current) {
                    setDetailStart(0);
                    setDetail(
                      pages.flatMap((p, index) =>
                        selected.has(p.id)
                          ? [{ ...p, position: index + 1 }]
                          : [],
                      ),
                    );
                  }
                }}
              >
                Enlarge selected pages
              </button>
              <div className="organize-tools">
                <div className="photo-actions organize-selection">
                  <button
                    aria-label="Select all pages"
                    onClick={() => setSelected(new Set(pages.map((p) => p.id)))}
                  >
                    <span className="organize-long">Select all pages</span>
                    <span className="organize-short" aria-hidden="true">
                      All
                    </span>
                  </button>
                  <button
                    aria-label="Clear selection"
                    onClick={() => setSelected(new Set())}
                  >
                    <span className="organize-long">Clear selection</span>
                    <span className="organize-short" aria-hidden="true">
                      None
                    </span>
                  </button>
                </div>
                <details className="move-options">
                  <summary>Move pages</summary>
                  <div className="photo-actions organize-move">
                    <button
                      aria-label="Move selected up"
                      disabled={!selected.size}
                      onClick={() => change(movePages(pages, selected, -1))}
                    >
                      <span className="organize-long">Move selected up</span>
                      <span className="organize-short" aria-hidden="true">
                        Up
                      </span>
                    </button>
                    <button
                      aria-label="Move selected down"
                      disabled={!selected.size}
                      onClick={() => change(movePages(pages, selected, 1))}
                    >
                      <span className="organize-long">Move selected down</span>
                      <span className="organize-short" aria-hidden="true">
                        Down
                      </span>
                    </button>
                  </div>
                  <div className="organize-position">
                    <label>
                      Move to position{" "}
                      <input
                        type="number"
                        min="1"
                        max={pages.length}
                        value={position}
                        onChange={(e) => setPosition(Number(e.target.value))}
                      />
                    </label>
                    <button
                      aria-label="Move selected to position"
                      disabled={
                        !selected.size ||
                        !Number.isInteger(position) ||
                        position < 1 ||
                        position > pages.length
                      }
                      onClick={() =>
                        change(placePages(pages, selected, position - 1))
                      }
                    >
                      <span className="organize-long">
                        Move selected to position
                      </span>
                      <span className="organize-short" aria-hidden="true">
                        Move
                      </span>
                    </button>
                  </div>
                </details>
                <div className="photo-actions organize-edit">
                  <button
                    aria-label="Rotate selected 90°"
                    disabled={!selected.size}
                    onClick={() =>
                      change(
                        pages.map((p) =>
                          selected.has(p.id)
                            ? { ...p, turns: (p.turns + 1) % 4 }
                            : p,
                        ),
                      )
                    }
                  >
                    <span className="organize-long">Rotate selected 90°</span>
                    <span className="organize-short" aria-hidden="true">
                      Rotate 90°
                    </span>
                  </button>
                  <button
                    aria-label="Delete selected pages"
                    disabled={!selected.size}
                    onClick={() => remove()}
                  >
                    <span className="organize-long">Delete selected pages</span>
                    <span className="organize-short" aria-hidden="true">
                      Delete
                    </span>
                  </button>
                </div>
              </div>
            </div>
          )}
          <div
            ref={host}
            className="organize-viewport"
            data-reorder-list
            role="group"
            aria-label="Draft page thumbnails"
            tabIndex={0}
            onScroll={(e) => setTop(e.currentTarget.scrollTop)}
            onKeyDown={(e) => {
              if (task.current) {
                // Block editing shortcuts, not keyboard navigation to Cancel.
                if (e.altKey && ["ArrowUp", "ArrowDown"].includes(e.key))
                  e.preventDefault();
                return;
              }
              if (e.altKey && ["ArrowUp", "ArrowDown"].includes(e.key)) {
                e.preventDefault();
                change(
                  movePages(pages, selected, e.key === "ArrowUp" ? -1 : 1),
                );
              }
              if (e.key === "PageDown" || e.key === "PageUp") {
                e.preventDefault();
                e.currentTarget.focus();
                e.currentTarget.scrollTop +=
                  (e.key === "PageDown" ? 1 : -1) * ROW * WINDOW;
              }
            }}
          >
            <div
              style={{
                height: Math.ceil(pages.length / columns) * ROW,
                position: "relative",
              }}
            >
              {visible.map((entry, i) => (
                <div
                  key={entry.id}
                  className="organize-row"
                  data-page-id={entry.id}
                  data-sort-index={start + i}
                  data-selected={selected.has(entry.id)}
                  style={{
                    position: "absolute",
                    top: Math.floor((start + i) / columns) * ROW,
                    left: `${(((start + i) % columns) * 100) / columns}%`,
                    height: ROW,
                    width: `${100 / columns}%`,
                  }}
                >
                  <button
                    className="page-face"
                    aria-label={`${selecting ? "Select" : "Enlarge"} original page ${entry.source + 1}`}
                    aria-pressed={
                      selecting ? selected.has(entry.id) : undefined
                    }
                    onClick={(e) => {
                      e.currentTarget.focus();
                      if (task.current) return;
                      if (selecting)
                        setSelected((old) => {
                          const next = new Set(old);
                          if (next.has(entry.id)) next.delete(entry.id);
                          else next.add(entry.id);
                          return next;
                        });
                      else {
                        setDetailStart(start + i);
                        setDetail(
                          pages.map((p, n) => ({ ...p, position: n + 1 })),
                        );
                      }
                    }}
                  >
                    <span
                      className="organize-thumbnail"
                      data-thumbnail={entry.id}
                    />
                    <span className="organize-page-label">
                      {selecting && (selected.has(entry.id) ? "✓ " : "○ ")}Page{" "}
                      {start + i + 1}
                    </span>
                  </button>
                  {!selecting && (
                    <div className="card-actions">
                      <CardMove
                        index={start + i}
                        count={pages.length}
                        label={`page ${start + i + 1}`}
                        disabled={busy}
                        move={(to) =>
                          change(placePages(pages, new Set([entry.id]), to))
                        }
                      />
                      <button
                        className="secondary"
                        aria-label={`Rotate page ${start + i + 1}`}
                        title="Rotate 90°"
                        onClick={() =>
                          change(
                            pages.map((p) =>
                              p.id === entry.id
                                ? { ...p, turns: (p.turns + 1) % 4 }
                                : p,
                            ),
                          )
                        }
                      >
                        ↻
                      </button>
                      <button
                        className="secondary"
                        aria-label={`Delete page ${start + i + 1}`}
                        title="Delete page"
                        onClick={() => remove(new Set([entry.id]))}
                      >
                        ×
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </fieldset>
        {pages.length < initial.length && (
          <details className="organize-deletion-options">
            <summary>
              {initial.length - pages.length} pages removed · link and structure
              options
            </summary>
            <label className="organize-deletion-policy">
              <input
                type="checkbox"
                disabled={busy}
                checked={adjustAssociations}
                onChange={(e) => {
                  if (!task.current) setAdjustAssociations(e.target.checked);
                }}
              />{" "}
              Adjust associations for deleted pages: disable links and bookmark
              jumps to those pages (keep their appearance and titles); remove
              their named destinations, page tags and form fields. Keep other
              content. Incomplete or ambiguous structures may still be refused.
            </label>
          </details>
        )}
        {!dirty && (
          <p className="task-guidance">
            Reorder, rotate or remove a page to create a new PDF.
          </p>
        )}
        {busy ? (
          <>
            <p role="status">Organizing and validating pages…</p>
            <button onClick={() => task.current?.abort()}>
              Cancel organize task
            </button>
          </>
        ) : (
          <div className="photo-actions organize-submit">
            <button
              aria-label="Apply page changes"
              disabled={!dirty}
              onClick={() =>
                void apply().then((ok) => {
                  if (ok) props.onClose();
                })
              }
            >
              <span className="organize-long">Create PDF →</span>
              <span className="organize-short" aria-hidden="true">
                Create PDF →
              </span>
            </button>
            <button
              aria-label="Cancel page changes"
              className="secondary"
              onClick={(event) => {
                event.currentTarget.focus({ preventScroll: true });
                guard(props.onClose);
              }}
            >
              <span className="organize-long">Cancel page changes</span>
              <span className="organize-short" aria-hidden="true">
                Cancel
              </span>
            </button>
          </div>
        )}
        {message && <p role="alert">{message}</p>}
        {detail && (
          <PageDetail
            preview={props.preview}
            entries={detail}
            initialIndex={detailStart}
            close={() => setDetail(null)}
          />
        )}
        {(busy || failure) && (
          <TaskNotice
            working={!!busy}
            message={busy ? "Organizing and checking your PDF…" : failure}
            close={() => {
              if (task.current) task.current.abort();
              else setFailure("");
            }}
            adjust={
              !busy &&
              failure.includes("still refers to a deleted page") &&
              !adjustAssociations
                ? () => {
                    setAdjustAssociations(true);
                    setFailure("");
                    void apply(true).then((ok) => {
                      if (ok) props.onClose();
                    });
                  }
                : undefined
            }
          />
        )}
        {pending && (
          <LeaveTaskDialog
            description="Your page order, rotation and deletion changes will be discarded."
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
