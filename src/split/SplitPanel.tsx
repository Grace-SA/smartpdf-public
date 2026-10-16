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
import type { Preview } from "../platform/engine";
import { PageStrip } from "../photos/PageStrip";
import { PageDetail } from "../organize/PageDetail";
import { PHOTO_LIMITS } from "../photos/model";
import { splitGroups, partNames, SPLIT_LIMIT } from "./model";
import { processSplit } from "./service";
import { analyticsReason, track } from "../analytics";
export type SplitHandle = { guard: (action: () => void) => void };
type Props = {
  file: File;
  preview: Preview;
  pages: number;
  retained: number;
  existingNames: string[];
  existingResults: number;
  publish: (
    files: File[],
    signal: AbortSignal,
    pageCounts: number[],
  ) => Promise<boolean>;
  onClose: () => void;
  onDirty: (value: boolean) => void;
  onBusy: (value: boolean) => void;
};
export const SplitPanel = forwardRef<SplitHandle, Props>(
  function SplitPanel(props, ref) {
    const [mode, setMode] = useState("groups"),
      [ranges, setRanges] = useState(`1-${props.pages}`);
    const [picked, setPicked] = useState<Set<number>>(() => new Set());
    const [separate, setSeparate] = useState(false);
    const [interval, setInterval] = useState("2");
    const [advanced, setAdvanced] = useState(false);
    const [rows, setRows] = useState([{ from: "1", to: String(props.pages) }]);
    const [detail, setDetail] = useState<number | null>(null);
    const updateRows = (next: typeof rows) => {
      setRows(next);
      setRanges(next.map((r) => `${r.from}-${r.to}`).join("\n"));
      setAdjust(false);
    };
    const [adjust, setAdjust] = useState(false);
    const [busy, setBusy] = useState(""),
      [message, setMessage] = useState("");
    const [failure, setFailure] = useState("");
    const [pending, setPending] = useState<{ action: () => void } | null>(null);
    const task = useRef<AbortController | null>(null);
    const dirty = mode !== "groups" || ranges !== `1-${props.pages}`;
    const { onDirty, onBusy } = props;
    useEffect(() => {
      onDirty(dirty);
    }, [dirty, onDirty]);
    useEffect(() => {
      onBusy(!!busy);
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
    const parsed = useMemo(() => {
      try {
        if (mode === "selected" && !picked.size)
          throw Error("Tap pages to include in your PDF.");
        return {
          groups: splitGroups(
            mode === "fixed"
              ? (() => {
                  const size = Number(interval);
                  if (
                    !/^\d+$/.test(interval) ||
                    !Number.isSafeInteger(size) ||
                    size < 1 ||
                    size > props.pages
                  )
                    throw Error(`Enter 1–${props.pages} pages per file.`);
                  return Array.from(
                    { length: Math.ceil(props.pages / size) },
                    (_, i) =>
                      `${i * size + 1}-${Math.min(props.pages, (i + 1) * size)}`,
                  ).join("\n");
                })()
              : mode === "selected"
                ? [...picked].sort((a, b) => a - b).join(separate ? "\n" : ",")
                : ranges,
            props.pages,
            mode === "each",
          ),
          error: "",
        };
      } catch (e) {
        return { groups: [], error: (e as Error).message };
      }
    }, [ranges, props.pages, mode, interval, picked, separate]);
    const count = parsed.groups.length;
    const capacityError =
      count &&
      (props.existingResults + count > SPLIT_LIMIT ||
        props.retained >= PHOTO_LIMITS.sessionBytes)
        ? "This batch would exceed 50 results or the 60 MiB task budget. Use fewer groups or smaller files."
        : "";
    const omitted =
      props.pages - parsed.groups.reduce((n, group) => n + group.length, 0);
    const canApply = count > 0 && !capacityError;
    async function apply(allowAdjustment = adjust) {
      if (task.current || !canApply) return false;
      const started = performance.now();
      track("process_start", "split", {
        fileCount: 1,
        totalBytes: props.file.size,
        pages: parsed.groups.reduce((sum, group) => sum + group.length, 0),
      });
      const controller = new AbortController();
      task.current = controller;
      let timeout = false;
      const timer = setTimeout(() => {
        timeout = true;
        controller.abort();
      }, PHOTO_LIMITS.timeoutMs);
      setBusy("Splitting PDF…");
      setMessage("");
      setFailure("");
      try {
        const outputs = await processSplit(
          props.file,
          parsed.groups,
          allowAdjustment,
          PHOTO_LIMITS.sessionBytes - props.retained,
          controller.signal,
          (done) => setBusy(`Created ${done} of ${count} PDFs…`),
        );
        const names = partNames(
          props.file.name,
          outputs.length,
          props.existingNames,
        );
        const files = outputs.map(
          (bytes, i) =>
            new File([bytes as Uint8Array<ArrayBuffer>], names[i]!, {
              type: "application/pdf",
            }),
        );
        if (controller.signal.aborted) throw new Error("Cancelled");
        setBusy("Checking the finished PDFs…");
        if (
          !(await props.publish(
            files,
            controller.signal,
            parsed.groups.map((group) => group.length),
          ))
        )
          throw new Error(
            "Split results could not be validated. Your source and previous results are unchanged.",
          );
        track("process_success", "split", {
          fileCount: files.length,
          totalBytes: files.reduce((sum, file) => sum + file.size, 0),
          pages: parsed.groups.reduce((sum, group) => sum + group.length, 0),
          durationMs: performance.now() - started,
        });
        return true;
      } catch (e) {
        track(
          controller.signal.aborted && !timeout
            ? "process_cancel"
            : "process_failure",
          "split",
          {
            durationMs: performance.now() - started,
            reason: analyticsReason(e, timeout),
          },
        );
        setFailure(
          timeout
            ? "Splitting took too long. No results were published. Try fewer groups."
            : controller.signal.aborted
              ? "Cancelled. Your source and previous results are unchanged."
              : (e as Error).message,
        );
        return false;
      } finally {
        clearTimeout(timer);
        task.current = null;
        setBusy("");
      }
    }
    return (
      <section className="split-task" aria-label="Split a PDF">
        <div className="split-document">
          <h2>{props.file.name}</h2>
          <p>
            {props.pages} pages ·{" "}
            {mode === "selected"
              ? `${picked.size} selected · Tap to include or exclude`
              : "Tap a page to enlarge"}
          </p>
          <fieldset className="split-mode-bar" disabled={!!busy}>
            <legend>Choose pages</legend>
            <label>
              Split mode{" "}
              <select
                value={mode}
                onChange={(e) => {
                  setMode(e.target.value);
                  setAdjust(false);
                }}
              >
                <option value="selected">Select pages</option>
                <option value="groups">Page groups</option>
                <option value="each">One file per page</option>
                <option value="fixed">Every N pages</option>
              </select>
            </label>
            {mode === "selected" && (
              <>
                <div className="photo-actions">
                  <button
                    className="secondary"
                    onClick={() => {
                      setPicked(
                        new Set(
                          Array.from({ length: props.pages }, (_, i) => i + 1),
                        ),
                      );
                      setAdjust(false);
                    }}
                  >
                    Select all
                  </button>
                  <button
                    className="secondary"
                    onClick={() => {
                      setPicked(new Set());
                      setAdjust(false);
                    }}
                  >
                    Clear
                  </button>
                </div>
                <label>
                  <input
                    type="checkbox"
                    checked={separate}
                    onChange={(e) => {
                      setSeparate(e.target.checked);
                      setAdjust(false);
                    }}
                  />{" "}
                  One PDF per selected page
                </label>
              </>
            )}
          </fieldset>
          <PageStrip
            doc={props.preview.doc}
            page={detail ?? 1}
            disabled={!!busy}
            selection={mode === "selected" ? picked : undefined}
            select={(n) => {
              if (mode !== "selected") setDetail(n);
              else {
                setPicked((old) => {
                  const next = new Set(old);
                  if (next.has(n)) next.delete(n);
                  else next.add(n);
                  return next;
                });
                setAdjust(false);
              }
            }}
            groups={parsed.groups}
          />
        </div>
        {detail !== null && (
          <PageDetail
            preview={props.preview}
            initialIndex={detail - 1}
            entries={Array.from({ length: props.pages }, (_, n) => ({
              id: String(n + 1),
              source: n,
              turns: 0,
              position: n + 1,
            }))}
            close={() => setDetail(null)}
          />
        )}
        <h2>Split settings</h2>
        <p>
          Keep your source and create separate PDFs. Preview or save each
          result, or continue editing it.
        </p>
        <details>
          <summary>File limits</summary>
          <p>
            Up to 50 retained results · 30 MiB / 200-page source · 60 MiB task.
            Every result is checked before download.
          </p>
        </details>
        <fieldset disabled={!!busy}>
          <legend>Choose split groups</legend>
          {mode === "fixed" && (
            <label>
              Pages per file
              <input
                aria-label="Pages per file"
                inputMode="numeric"
                value={interval}
                onChange={(e) => {
                  setInterval(e.target.value);
                  setAdjust(false);
                }}
              />
            </label>
          )}
          {mode === "groups" && (
            <>
              <label>
                <input
                  type="checkbox"
                  checked={advanced}
                  onChange={(e) => {
                    setAdvanced(e.target.checked);
                    if (!e.target.checked) updateRows(rows);
                  }}
                />{" "}
                Advanced page groups
              </label>
              {advanced ? (
                <label>
                  Page groups, one per line
                  <textarea
                    rows={4}
                    maxLength={10000}
                    value={ranges}
                    placeholder={"1-3\n4-7"}
                    onChange={(e) => {
                      setRanges(e.target.value);
                      setAdjust(false);
                    }}
                  />
                </label>
              ) : (
                <>
                  {rows.map((row, i) => (
                    <div className="range-row" key={i}>
                      <label>
                        From page
                        <input
                          aria-label={`Range ${i + 1} from`}
                          inputMode="numeric"
                          value={row.from}
                          onChange={(e) =>
                            updateRows(
                              rows.map((r, n) =>
                                n === i ? { ...r, from: e.target.value } : r,
                              ),
                            )
                          }
                        />
                      </label>
                      <label>
                        To page
                        <input
                          aria-label={`Range ${i + 1} to`}
                          inputMode="numeric"
                          value={row.to}
                          onChange={(e) =>
                            updateRows(
                              rows.map((r, n) =>
                                n === i ? { ...r, to: e.target.value } : r,
                              ),
                            )
                          }
                        />
                      </label>
                      <button
                        className="secondary"
                        aria-label={`Remove range ${i + 1}`}
                        disabled={rows.length === 1}
                        onClick={() =>
                          updateRows(rows.filter((_, n) => n !== i))
                        }
                      >
                        ×
                      </button>
                    </div>
                  ))}
                  <button
                    className="secondary"
                    disabled={rows.length >= 50}
                    onClick={() => updateRows([...rows, { from: "", to: "" }])}
                  >
                    + Add range
                  </button>
                  {!ranges && (
                    <button
                      className="secondary"
                      onClick={() => updateRows(rows)}
                    >
                      Use this range
                    </button>
                  )}
                </>
              )}
            </>
          )}
          {parsed.error && <p role="alert">{parsed.error}</p>}
          {!!count && (
            <>
              <p role="status">
                {count} results · {omitted} pages omitted from results. The
                source keeps all {props.pages} pages.
              </p>
              <ol className="split-plan">
                {parsed.groups.map((group, i) => (
                  <li key={i}>
                    Part {i + 1}: {group.length} pages (
                    {group.map((n) => n + 1).join(", ")})
                  </li>
                ))}
              </ol>
            </>
          )}
          {!!capacityError && <p role="alert">{capacityError}</p>}
          <details className="association-options">
            <summary>Links and document structure</summary>
            <label className="confirm-line">
              <input
                type="checkbox"
                checked={adjust}
                onChange={(e) => setAdjust(e.target.checked)}
              />{" "}
              Allow links and structure to be adjusted for excluded pages.
            </label>
            <p>
              Links and bookmarks pointing outside a part will lose their jump
              targets, but keep their appearance and titles. Named destinations,
              tags and form fields belonging to excluded pages are removed. Your
              source stays unchanged. Ambiguous structures are still refused.
            </p>
          </details>
        </fieldset>
        {busy ? (
          <div role="status">
            <p>{busy}</p>
            <button onClick={() => task.current?.abort()}>
              Cancel split task
            </button>
          </div>
        ) : (
          <div className="photo-actions">
            <button
              disabled={!canApply}
              onClick={() =>
                void apply().then((ok) => {
                  if (ok) props.onClose();
                })
              }
            >
              Split PDF →
            </button>
            <button
              className="secondary"
              onClick={(event) => {
                event.currentTarget.focus({ preventScroll: true });
                guard(props.onClose);
              }}
            >
              Cancel task
            </button>
          </div>
        )}
        {message && <p role="alert">{message}</p>}
        {(busy || failure) && (
          <TaskNotice
            working={!!busy}
            message={busy ? busy : failure}
            close={() => {
              if (task.current) task.current.abort();
              else setFailure("");
            }}
            adjust={
              !busy &&
              failure.includes("still refers to a deleted page") &&
              !adjust
                ? () => {
                    setAdjust(true);
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
            description="Your page selection and split settings will be cleared."
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
