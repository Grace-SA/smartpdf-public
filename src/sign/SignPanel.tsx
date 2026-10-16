import { ContinuousCanvas } from "./ContinuousCanvas";
import { readingLayout, readingPage, readingWindow } from "./reading-layout";
import { PagePicker, PageThumbnails } from "./PagePicker";
import {
  forwardRef,
  useEffect,
  useCallback,
  useMemo,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import type { Preview } from "../platform/engine";
import { LeaveTaskDialog } from "../LeaveTaskDialog";
import { ConfirmDialog } from "../ConfirmDialog";
import { SignatureCreator } from "./SignatureCreator";
import { requestSign } from "./service";
import {
  newSignatureId,
  constrain,
  displaySize,
  fits,
  SIGN_LIMITS,
  type Geometry,
  type Placement,
  type SignatureAsset,
} from "./model";
import "./sign.css";
import { analyticsReason, track } from "../analytics";
export type SignHandle = { guard: (action: () => void) => void };
type Props = {
  file: File;
  preview: Preview;
  apply: (file: File, signal: AbortSignal) => Promise<boolean>;
  onDirty: (v: boolean) => void;
  onBusy: (v: boolean) => void;
};
export const SignPanel = forwardRef<SignHandle, Props>(function SignPanel(
  { file, preview, apply, onDirty, onBusy },
  ref,
) {
  const [pagesOpen, setPagesOpen] = useState(false);
  const [geometry, setGeometry] = useState<Geometry[]>([]),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false),
    [stage, setStage] = useState("Checking PDF…"),
    [page, setPage] = useState(0),
    [zoom, setZoom] = useState(1),
    [width, setWidth] = useState(600),
    [height, setHeight] = useState(600),
    [creator, setCreator] = useState(false),
    [assets, setAssets] = useState<SignatureAsset[]>([]),
    [asset, setAsset] = useState<string | null>(null),
    [plan, setPlan] = useState<Placement[]>([]),
    [past, setPast] = useState<Placement[][]>([]),
    [future, setFuture] = useState<Placement[][]>([]),
    [selected, setSelected] = useState<string | null>(null),
    [pending, setPending] = useState<"add" | "move" | null>(null),
    [adjust, setAdjust] = useState<Placement | null>(null),
    [leave, setLeave] = useState<(() => void) | null>(null),
    [dirty, setDirty] = useState(false),
    [list, setList] = useState(false),
    [dragged, setDragged] = useState<Placement | null>(null);
  const retainedUrls = useRef(new Set<string>());
  const pageNodes = useRef(new Map<number, HTMLDivElement>());
  const [scrollTop, setScrollTop] = useState(0);
  const [readyPages, setReadyPages] = useState(new Set<number>());
  const [railOpen, setRailOpen] = useState(true);
  const ready = useCallback((index: number, value: boolean) => {
    setReadyPages((old) => {
      if (old.has(index) === value) return old;
      const next = new Set(old);
      if (value) next.add(index);
      else next.delete(index);
      return next;
    });
  }, []);
  const messageRef = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    const urls = retainedUrls.current;
    return () => {
      for (const url of urls) URL.revokeObjectURL(url);
    };
  }, []);
  const viewport = useRef<HTMLDivElement>(null),
    job = useRef<AbortController | null>(null),
    gesture = useRef<{
      x: number;
      y: number;
      p?: Placement;
      resize?: boolean;
      scroll?: number;
    } | null>(null);
  const g = geometry[page],
    size = g ? displaySize(g) : null,
    current = plan.find((p) => p.id === selected),
    activeAsset = assets.find((a) => a.id === asset),
    blocked = busy || !!stage;
  const layout = useMemo(
    () => readingLayout(geometry, width, height, zoom),
    [geometry, width, height, zoom],
  );
  const previousLayout = useRef(layout);
  const visiblePages = readingWindow(layout, scrollTop, height + 40);
  function goToPage(next: number) {
    if (blocked || next < 0 || next >= geometry.length) return;
    if (viewport.current) viewport.current.scrollTop = layout[next]!.top;
    setScrollTop(layout[next]!.top);
    setPage(next);
    setSelected(null);
  }
  useLayoutEffect(() => {
    const el = viewport.current,
      old = previousLayout.current;
    previousLayout.current = layout;
    if (!el || !old.length || !layout.length) return;
    const anchor = readingPage(old, el.scrollTop + 24);
    const fraction =
      (el.scrollTop - old[anchor]!.top) / (old[anchor]!.height + 48);
    el.scrollTop =
      layout[anchor]!.top + fraction * (layout[anchor]!.height + 48);
    setScrollTop(el.scrollTop);
  }, [layout]);
  useImperativeHandle(
    ref,
    () => ({
      guard(action) {
        if (blocked) return;
        if (dirty) setLeave(() => action);
        else action();
      },
    }),
    [blocked, dirty],
  );
  useEffect(() => {
    onDirty(dirty);
  }, [dirty, onDirty]);
  useEffect(() => {
    onBusy(busy);
    return () => onBusy(false);
  }, [busy, onBusy]);
  useEffect(() => {
    const c = new AbortController();
    job.current = c;
    void requestSign(file, c.signal)
      .then((result) => {
        if (!c.signal.aborted) {
          setGeometry(result as Geometry[]);
          setStage("");
        }
      })
      .catch((e) => {
        if (!c.signal.aborted) {
          setMessage(e.message);
          setStage("");
        }
      });
    return () => {
      c.abort();
      job.current?.abort();
    };
  }, [file]);
  useEffect(() => {
    const el = viewport.current;
    if (!el) return;
    const resize = () => {
      // Scrollbars depend on the rendered page. Never feed their changing
      // client size back into the next render's fit calculation.
      const rect = el.getBoundingClientRect();
      setWidth(Math.min(1000, Math.max(100, Math.round(rect.width) - 56)));
      setHeight(Math.max(100, Math.round(rect.height) - 40));
    };
    const obs = new ResizeObserver(resize);
    obs.observe(el);
    resize();
    return () => obs.disconnect();
  }, []);
  useEffect(() => {
    if (creator || adjust || pagesOpen || busy) return;
    if (pending) {
      viewport.current?.focus({ preventScroll: true });
      return;
    }
    if (selected && current) {
      const target = pageNodes.current
        .get(current.page)
        ?.querySelector<HTMLElement>(".sign-placement.selected");
      target?.focus({ preventScroll: true });
      if (!gesture.current?.p)
        target?.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
  }, [
    selected,
    pending,
    creator,
    adjust,
    pagesOpen,
    busy,
    current,
    width,
    height,
    zoom,
  ]);
  function commit(next: Placement[]) {
    setPast((h) => [...h, plan].slice(-50));
    setFuture([]);
    setPlan(next);
    setDirty(true);
  }
  useEffect(() => {
    if (message && !busy)
      messageRef.current?.scrollIntoView({ block: "nearest" });
  }, [message, busy]);
  function update(p: Placement) {
    commit(plan.map((old) => (old.id === p.id ? p : old)));
  }
  function placeAt(x: number, y: number, targetPage = page) {
    const g = geometry[targetPage];
    const size = g ? displaySize(g) : null;
    if (!g || !pending) return;
    setPage(targetPage);
    if (pending === "move" && current) {
      update(
        constrain(
          {
            ...current,
            page: targetPage,
            x: x - current.width / 2,
            y: y - current.height / 2,
          },
          g,
        ),
      );
    } else if (activeAsset) {
      if (plan.length >= SIGN_LIMITS.instances) {
        setMessage("Use up to 100 signatures in one task.");
        return;
      }
      const w = Math.min(113.386, size!.width * 0.4),
        p = constrain(
          {
            id: newSignatureId(),
            asset: activeAsset.id,
            page: targetPage,
            x: x - w / 2,
            y: y - (w * activeAsset.height) / activeAsset.width / 2,
            width: w,
            height: (w * activeAsset.height) / activeAsset.width,
          },
          g,
        );
      commit([...plan, p]);
      setSelected(p.id);
    }
    setPending(null);
  }
  function useAsset(a: SignatureAsset) {
    if (!assets.some((old) => old.id === a.id)) {
      if (
        assets.length >= SIGN_LIMITS.assets ||
        assets.reduce((n, b) => n + b.bytes.length, 0) + a.bytes.length >
          SIGN_LIMITS.totalBytes
      ) {
        setMessage(
          "Signature image budget reached. Start a new task for more images.",
        );
        return false;
      }
      setAssets((old) => [...old, a]);
    }
    retainedUrls.current.add(a.url);
    setAsset(a.id);
    setCreator(false);
    setPending("add");
    setDirty(true);
    setMessage("");
    return true;
  }
  async function generate() {
    if (!plan.length || blocked || pending) return;
    const started = performance.now();
    track("process_start", "sign", {
      fileCount: 1,
      totalBytes: file.size,
      pages: geometry.length,
    });
    const c = new AbortController();
    job.current = c;
    setBusy(true);
    setMessage("");
    setStage("Checking your PDF…");
    try {
      const result = (await requestSign(
        file,
        c.signal,
        assets,
        plan,
        setStage,
      )) as Uint8Array;
      if (c.signal.aborted) throw new DOMException("Aborted", "AbortError");
      setStage("Checking the final preview…");
      const output = new File(
        [result as Uint8Array<ArrayBuffer>],
        file.name.replace(/\.pdf$/i, "") + "-signed.pdf",
        { type: "application/pdf" },
      );
      const applied = await apply(output, c.signal);
      if (c.signal.aborted) throw new DOMException("Aborted", "AbortError");
      if (!applied)
        throw new Error(
          "The output could not be opened. Your draft is unchanged.",
        );
      track("process_success", "sign", {
        fileCount: 1,
        totalBytes: output.size,
        pages: geometry.length,
        durationMs: performance.now() - started,
      });
    } catch (e) {
      track(c.signal.aborted ? "process_cancel" : "process_failure", "sign", {
        durationMs: performance.now() - started,
        reason: analyticsReason(e),
      });
      if (!c.signal.aborted)
        setMessage(
          e instanceof Error
            ? e.message
            : "Signing failed. Your draft is unchanged.",
        );
    } finally {
      if (job.current === c) {
        job.current = null;
        setBusy(false);
        setStage("");
      }
    }
  }
  const context = current && !pending && (
    <div className="sign-object-actions">
      <button className="secondary" onClick={() => setPending("move")}>
        Move
      </button>
      <button className="secondary" onClick={() => setAdjust({ ...current })}>
        Size
      </button>
      <button
        className="secondary"
        onClick={() => {
          commit(plan.filter((p) => p.id !== current.id));
          setSelected(null);
        }}
      >
        Delete
      </button>
    </div>
  );
  const actions = (
    <>
      {pending ? (
        <>
          <p>
            {pending === "add"
              ? "Scroll to the right page, then tap to place your signature."
              : "Scroll to your destination, then tap a new position."}
          </p>
          <button
            disabled={blocked || !readyPages.has(page)}
            onClick={() => placeAt(size!.width / 2, size!.height / 2)}
          >
            Place at page center
          </button>
          <button className="secondary" onClick={() => setPending(null)}>
            Cancel placement
          </button>
        </>
      ) : plan.length ? (
        <>
          <div className="sign-row">
            <button
              className="secondary"
              onClick={() => {
                setPending("add");
                setSelected(null);
              }}
            >
              Add another
            </button>
            <button className="secondary" onClick={() => setCreator(true)}>
              New signature
            </button>
          </div>
          <button
            disabled={blocked || !plan.length}
            onClick={() => void generate()}
          >
            Create signed PDF
          </button>
        </>
      ) : (
        <button disabled={blocked || !g} onClick={() => setCreator(true)}>
          Add signature
        </button>
      )}
    </>
  );
  return (
    <section
      className="sign-task"
      aria-label="Sign PDF workspace"
      onKeyDown={(e) => {
        if (e.key === "Escape" && pending && !blocked) {
          e.preventDefault();
          setPending(null);
        }
      }}
    >
      <p className="sign-filename">{file.name}</p>
      <div className="sign-toolbar">
        <div
          className="sign-page-navigation"
          role="group"
          aria-label="Page navigation"
        >
          <button
            className="secondary"
            aria-label="Previous page"
            disabled={blocked || page === 0}
            onClick={() => goToPage(page - 1)}
          >
            ← Previous
          </button>
          <label>
            Page{" "}
            <input
              type="number"
              aria-label="Signature page"
              min={1}
              max={geometry.length || 1}
              value={page + 1}
              disabled={blocked}
              onChange={(e) => {
                const n = Number(e.target.value);
                if (Number.isInteger(n) && n >= 1 && n <= geometry.length) {
                  goToPage(n - 1);
                }
              }}
            />
            <span> / {geometry.length || preview.doc.numPages}</span>
          </label>
          <button
            className="secondary"
            aria-label="Next page"
            disabled={blocked || page >= geometry.length - 1}
            onClick={() => goToPage(page + 1)}
          >
            Next →
          </button>
        </div>
        <button
          className="secondary"
          disabled={blocked}
          onClick={() => setPagesOpen(true)}
        >
          Pages
        </button>
        <label>
          Zoom{" "}
          <select
            aria-label="Signature zoom"
            value={zoom}
            disabled={busy}
            onChange={(e) => setZoom(Number(e.target.value))}
          >
            <option value={0.75}>75% width</option>
            <option value={1}>Fit width</option>
            <option value={-1}>Fit page</option>
            <option value={1.5}>150% width</option>
            <option value={2}>200% width</option>
          </select>
        </label>
        <button
          className="secondary"
          disabled={!past.length || blocked || !!pending}
          onClick={() => {
            setFuture((h) => [plan, ...h]);
            setPlan(past.at(-1)!);
            setPast((h) => h.slice(0, -1));
            setSelected(null);
          }}
        >
          Undo
        </button>
        <button
          className="secondary"
          disabled={!future.length || blocked || !!pending}
          onClick={() => {
            setPast((h) => [...h, plan]);
            setPlan(future[0]!);
            setFuture((h) => h.slice(1));
            setSelected(null);
          }}
        >
          Redo
        </button>
      </div>
      <div className={`sign-layout ${railOpen ? "has-page-rail" : ""}`}>
        <nav className="sign-page-rail" aria-label="Page thumbnails">
          <button
            className="secondary"
            onClick={() => setRailOpen(!railOpen)}
            aria-label={railOpen ? "Hide thumbnails" : "Show thumbnails"}
          >
            {railOpen ? "Hide pages" : "Pages"}
          </button>
          {railOpen && (
            <PageThumbnails
              preview={preview}
              counts={geometry.map(
                (_, i) => plan.filter((p) => p.page === i).length,
              )}
              current={page}
              choose={goToPage}
            />
          )}
        </nav>
        <div
          className="sign-viewport"
          ref={viewport}
          tabIndex={0}
          aria-label="PDF document. Scroll to read all pages."
          onScroll={() => {
            const el = viewport.current;
            if (!el) return;
            setScrollTop(el.scrollTop);
            const next = readingPage(
              layout,
              el.scrollTop + Math.min(el.clientHeight * 0.28, 200),
            );
            if (next !== page && !gesture.current?.p) {
              setPage(next);
              if (!pending) setSelected(null);
            }
          }}
        >
          {layout.map((sheet, index) => {
            const g = geometry[index]!,
              size = displaySize(g);
            return (
              <div
                className="sign-sheet"
                key={index}
                data-page={index + 1}
                data-current={index === page ? "true" : undefined}
                style={{ width: sheet.width }}
              >
                <div className="sign-sheet-label">
                  Page {index + 1} of {geometry.length}
                </div>
                <div
                  ref={(node) => {
                    if (node) pageNodes.current.set(index, node);
                    else pageNodes.current.delete(index);
                  }}
                  tabIndex={-1}
                  className={`sign-paper ${pending ? "is-placing" : ""}`}
                  style={{
                    width: sheet.width,
                    height: sheet.height,
                  }}
                  onPointerDown={(e) => {
                    if (
                      e.target === e.currentTarget ||
                      e.target instanceof HTMLCanvasElement
                    ) {
                      gesture.current = {
                        x: e.clientX,
                        y: e.clientY,
                        scroll: viewport.current?.scrollTop,
                      };
                    }
                  }}
                  onPointerUp={(e) => {
                    const start = gesture.current;
                    gesture.current = null;
                    if (!start || start.p || blocked || !readyPages.has(index))
                      return;
                    if (
                      Math.abs(
                        (viewport.current?.scrollTop ?? 0) -
                          (start.scroll ?? 0),
                      ) > 4
                    )
                      return;
                    if (
                      Math.hypot(start.x - e.clientX, start.y - e.clientY) > 8
                    )
                      return;
                    if (pending) {
                      const r = e.currentTarget.getBoundingClientRect();
                      placeAt(
                        ((e.clientX - r.left) / r.width) * size.width,
                        ((e.clientY - r.top) / r.height) * size.height,
                        index,
                      );
                    } else setSelected(null);
                  }}
                >
                  <ContinuousCanvas
                    preview={preview}
                    index={index}
                    width={sheet.width}
                    height={sheet.height}
                    active={visiblePages.has(index)}
                    ready={ready}
                  />
                  {readyPages.has(index) &&
                    plan
                      .filter((p) => p.page === index)
                      .map((original) => {
                        const p =
                            dragged?.id === original.id ? dragged : original,
                          a = assets.find((a) => a.id === p.asset)!;
                        return (
                          <div
                            key={p.id}
                            role="button"
                            tabIndex={blocked ? -1 : 0}
                            aria-label={`Signature ${plan.indexOf(original) + 1} on page ${index + 1}`}
                            aria-pressed={selected === p.id}
                            className={`sign-placement ${selected === p.id ? "selected" : ""}`}
                            style={{
                              left: (p.x / size.width) * 100 + "%",
                              top: (p.y / size.height) * 100 + "%",
                              width: (p.width / size.width) * 100 + "%",
                              height: (p.height / size.height) * 100 + "%",
                            }}
                            onKeyDown={(e) => {
                              if (blocked || pending) return;
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                setPage(index);
                                setSelected(p.id);
                                return;
                              }
                              if (e.key === "Delete" || e.key === "Backspace") {
                                e.preventDefault();
                                commit(plan.filter((s) => s.id !== p.id));
                                setSelected(null);
                                return;
                              }
                              const step = e.shiftKey ? 10 : 1;
                              const dx =
                                  e.key === "ArrowLeft"
                                    ? -step
                                    : e.key === "ArrowRight"
                                      ? step
                                      : 0,
                                dy =
                                  e.key === "ArrowUp"
                                    ? -step
                                    : e.key === "ArrowDown"
                                      ? step
                                      : 0;
                              if (dx || dy) {
                                e.preventDefault();
                                update(
                                  constrain(
                                    { ...p, x: p.x + dx, y: p.y + dy },
                                    g!,
                                  ),
                                );
                              }
                            }}
                            onPointerDown={(e) => {
                              if (blocked || pending || !e.isPrimary) return;
                              e.stopPropagation();
                              setPage(index);
                              if (
                                e.pointerType === "touch" &&
                                selected !== p.id
                              ) {
                                gesture.current = {
                                  x: e.clientX,
                                  y: e.clientY,
                                  scroll: viewport.current?.scrollTop,
                                };
                                return;
                              }
                              setSelected(p.id);
                              e.currentTarget.setPointerCapture(e.pointerId);
                              gesture.current = {
                                x: e.clientX,
                                y: e.clientY,
                                p: { ...p },
                                resize:
                                  (e.target as HTMLElement).dataset.resize ===
                                  "true",
                              };
                            }}
                            onPointerMove={(e) => {
                              const start = gesture.current;
                              if (!start?.p || start.p.id !== p.id || blocked)
                                return;
                              const scale =
                                size.width /
                                e.currentTarget.parentElement!.getBoundingClientRect()
                                  .width;
                              const dx = (e.clientX - start.x) * scale,
                                dy = (e.clientY - start.y) * scale;
                              const next = start.resize
                                ? {
                                    ...start.p,
                                    width: Math.max(4, start.p.width + dx),
                                    height:
                                      (Math.max(4, start.p.width + dx) *
                                        start.p.height) /
                                      start.p.width,
                                  }
                                : {
                                    ...start.p,
                                    x: start.p.x + dx,
                                    y: start.p.y + dy,
                                  };
                              setDragged(constrain(next, g!));
                            }}
                            onPointerUp={(e) => {
                              e.stopPropagation();
                              if (gesture.current?.p && dragged)
                                update(dragged);
                              else if (
                                gesture.current &&
                                !gesture.current.p &&
                                Math.hypot(
                                  e.clientX - gesture.current.x,
                                  e.clientY - gesture.current.y,
                                ) <= 8
                              )
                                setSelected(p.id);
                              gesture.current = null;
                              setDragged(null);
                            }}
                            onPointerCancel={() => {
                              gesture.current = null;
                              setDragged(null);
                            }}
                          >
                            <img src={a.url} draggable={false} alt="" />
                            {selected === p.id && (
                              <span
                                data-resize="true"
                                className="sign-resize"
                                aria-hidden="true"
                              />
                            )}
                          </div>
                        );
                      })}
                </div>
              </div>
            );
          })}
        </div>
        <aside className="sign-sidebar">
          <h2>Your signature</h2>
          {activeAsset ? (
            <img
              className="sign-asset"
              src={activeAsset.url}
              alt="Current signature"
            />
          ) : (
            <p>
              Draw, type your name or choose an image. Then place it on the
              page.
            </p>
          )}
          {context}
          {plan.length > 0 && (
            <button className="secondary" onClick={() => setList(!list)}>
              {plan.length} signature{plan.length === 1 ? "" : "s"} · review
              placements
            </button>
          )}
          {list && (
            <ul className="sign-placements">
              {plan.map((p, i) => (
                <li key={p.id}>
                  <button
                    className="secondary"
                    onClick={() => {
                      goToPage(p.page);
                      setSelected(p.id);
                      setList(false);
                    }}
                  >
                    Page {p.page + 1} · Signature {i + 1}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="sign-actions">{actions}</div>
          <p className="sign-hint">
            Visible signature only. No certificate or identity verification.
            Your original stays unchanged.
          </p>
        </aside>
      </div>
      {message && (
        <p ref={messageRef} role="alert" className="sign-message">
          {message}
        </p>
      )}
      {stage && !busy && <p role="status">{stage}</p>}
      {pagesOpen && (
        <PagePicker
          preview={preview}
          counts={geometry.map(
            (_, i) => plan.filter((p) => p.page === i).length,
          )}
          close={() => setPagesOpen(false)}
          choose={(i) => {
            goToPage(i);
            setPagesOpen(false);
          }}
        />
      )}
      <SignatureCreator
        open={creator}
        close={() => setCreator(false)}
        onUse={useAsset}
        dirty={() => setDirty(true)}
      />
      {adjust && g && (
        <ConfirmDialog
          title="Signature size"
          cancelLabel="Cancel"
          onCancel={() => setAdjust(null)}
          action={
            <button
              disabled={!fits(adjust, g)}
              onClick={() => {
                update(adjust);
                setAdjust(null);
              }}
            >
              Done
            </button>
          }
        >
          <div className="sign-size">
            <button
              className="secondary"
              aria-label="Smaller signature"
              onClick={() =>
                setAdjust({
                  ...adjust,
                  width: adjust.width * 0.95,
                  height: adjust.height * 0.95,
                })
              }
            >
              −
            </button>
            <strong>{((adjust.width * 25.4) / 72).toFixed(1)} mm</strong>
            <button
              className="secondary"
              aria-label="Larger signature"
              onClick={() =>
                setAdjust({
                  ...adjust,
                  width: adjust.width * 1.05,
                  height: adjust.height * 1.05,
                })
              }
            >
              +
            </button>
          </div>
          <p>Width · proportions stay the same</p>
          <details>
            <summary>Precise position &amp; size</summary>
            {(["x", "y", "width"] as const).map((key) => (
              <label key={key}>
                {key === "x"
                  ? "X from left"
                  : key === "y"
                    ? "Y from top"
                    : "Width"}{" "}
                (mm)
                <input
                  type="number"
                  min={0}
                  step={0.1}
                  value={
                    Number.isFinite(adjust[key])
                      ? Number(((adjust[key] * 25.4) / 72).toFixed(2))
                      : ""
                  }
                  onChange={(e) => {
                    const value =
                      e.target.value === ""
                        ? NaN
                        : (Number(e.target.value) * 72) / 25.4;
                    setAdjust({
                      ...adjust,
                      [key]: value,
                      ...(key === "width"
                        ? { height: (value * current!.height) / current!.width }
                        : {}),
                    });
                  }}
                />
              </label>
            ))}
          </details>
          {!fits(adjust, g) && (
            <p role="alert">
              Keep a positive-sized signature entirely inside the page.
            </p>
          )}
        </ConfirmDialog>
      )}
      {busy && (
        <ConfirmDialog
          title="Creating your PDF…"
          cancelLabel="Cancel processing"
          onCancel={() => {
            job.current?.abort();
            setMessage("Cancelled. Your signature draft is unchanged.");
          }}
          action={null}
        >
          <p role="status">{stage}</p>
          <progress />
        </ConfirmDialog>
      )}
      {leave && (
        <LeaveTaskDialog
          description="Your selected PDF and signature draft will be cleared."
          keep={() => setLeave(null)}
          leave={() => {
            const action = leave;
            setLeave(null);
            action();
          }}
        />
      )}
    </section>
  );
});
