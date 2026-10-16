import { FilePicker } from "../FilePicker";
import { LeaveTaskDialog } from "../LeaveTaskDialog";
import { TaskNotice } from "../TaskNotice";
import { CardMove } from "../CardMove";
import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { reasons } from "../copy";
import { LIMITS } from "../core/contracts";
import { PHOTO_LIMITS, photoCopy, safeFilename } from "../photos/model";
import { processPdfs } from "./service";
import { analyticsReason, track } from "../analytics";
export { prepareCombine } from "./service";
export type CombineHandle = { guard: (action: () => void) => void };
export type CombineProps = {
  ready?: boolean;
  seed?: File;
  seedFiles?: File[];
  onSeedConsumed?: () => void;
  pauseInitialInput?: boolean;
  thumbnail: (file: File, signal: AbortSignal) => Promise<string>;
  previewFile: (file: File) => void;
  retainedFiles: File[];
  apply: (file: File, signal: AbortSignal) => Promise<boolean>;
  onClose: () => void;
  onDirty: (value: boolean) => void;
  onBusy: (value: boolean) => void;
};
type Item = {
  id: number;
  file: File;
  pages?: number;
  error?: string;
  thumbnail?: string;
};
export const CombinePanel = forwardRef<CombineHandle, CombineProps>(
  function CombinePanel(props, ref) {
    const [items, setItems] = useState<Item[]>([]);
    const [busy, setBusy] = useState("");
    const [message, setMessage] = useState("");
    const [failure, setFailure] = useState("");
    const [dirty, setDirty] = useState(false);
    const [name, setName] = useState("Combined.pdf");
    const [pending, setPending] = useState<{ action: () => void } | null>(null);
    const task = useRef<AbortController | null>(null),
      nextId = useRef(0);
    const { onDirty, onBusy } = props;
    useEffect(() => {
      onDirty(dirty && items.length > 0);
    }, [dirty, items.length, onDirty]);
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
      if (dirty && items.length) setPending({ action });
      else action();
    }
    useImperativeHandle(ref, () => ({ guard }));
    const heldBytes = (files: File[]) =>
      [...new Set([...props.retainedFiles, ...files])].reduce(
        (n, f) => n + f.size,
        0,
      );
    const input = items.reduce((n, i) => n + i.file.size, 0);
    const pages = items.reduce((n, i) => n + (i.pages ?? 0), 0);
    const held = heldBytes(items.map((i) => i.file));
    const estimate = Math.ceil(input * 1.2) + 65536;
    const overBudget = held + estimate > PHOTO_LIMITS.sessionBytes;
    const canApply =
      props.ready !== false &&
      items.length >= 2 &&
      !items.some((i) => i.error || !i.pages) &&
      pages <= 200 &&
      !overBudget;
    async function add(files: File[], initial = false) {
      if (task.current || !files.length) return;
      if (
        items.length + files.length > 10 ||
        input + files.reduce((n, f) => n + f.size, 0) > LIMITS.bytes
      ) {
        setMessage("Use at most 10 PDFs and 30 MiB of input in this task.");
        return;
      }
      if (
        heldBytes([...items.map((i) => i.file), ...files]) >
        PHOTO_LIMITS.sessionBytes
      ) {
        setMessage(photoCopy.budget);
        return;
      }
      const controller = new AbortController();
      task.current = controller;
      let timeout = false;
      const timer = setTimeout(() => {
        timeout = true;
        controller.abort();
      }, LIMITS.timeoutMs);
      setMessage("");
      setBusy("Checking PDFs…");
      const added: Item[] = [];
      try {
        for (const file of files) {
          const item: Item = { id: ++nextId.current, file };
          try {
            if (!/\.pdf$/i.test(file.name) || !file.size)
              throw new Error("Choose a non-empty PDF file.");
            const { result } = await processPdfs(
              "inspect",
              [file],
              controller.signal,
              setBusy,
            );
            if (!result?.ok)
              item.error =
                result && !result.ok
                  ? result.detail ||
                    (result.reasons ?? (result.reason ? [result.reason] : []))
                      .map((r) => reasons[r])
                      .join(" ") ||
                    "This PDF cannot be combined safely."
                  : "This PDF could not be checked.";
            else {
              item.pages = result.pages;
              try {
                item.thumbnail = await props.thumbnail(file, controller.signal);
              } catch {
                /* A missing thumbnail must not change merge eligibility. */
              }
            }
          } catch (error) {
            if (controller.signal.aborted) break;
            item.error =
              error instanceof Error
                ? error.message
                : "This PDF could not be checked.";
          }
          added.push(item);
        }
        if (!controller.signal.aborted) {
          setItems((old) => [...old, ...added]);
          if (!initial) setDirty(true);
        } else
          setMessage(
            timeout
              ? "Checking PDFs took too long. This batch was not added. Try fewer or smaller PDFs."
              : "Cancelled. This batch was not added. Your earlier inputs and document are unchanged.",
          );
      } finally {
        clearTimeout(timer);
        task.current = null;
        setBusy("");
      }
    }
    const initialize = useRef<(() => void) | null>(() => {
      if (props.seedFiles?.length)
        void add(props.seedFiles).finally(() => props.onSeedConsumed?.());
      else if (props.seed) void add([props.seed], true);
    });
    useEffect(() => {
      if (props.pauseInitialInput) return;
      const start = initialize.current;
      initialize.current = null;
      start?.();
    }, [props.pauseInitialInput]);
    function move(id: number, to: number) {
      if (task.current) return;
      setItems((old) => {
        const from = old.findIndex((i) => i.id === id);
        if (from < 0 || to < 0 || to >= old.length) return old;
        const next = [...old];
        next.splice(to, 0, next.splice(from, 1)[0]!);
        return next;
      });
      setDirty(true);
    }
    async function apply() {
      if (task.current || !canApply) return false;
      const started = performance.now();
      track("process_start", "combine", {
        fileCount: items.length,
        totalBytes: items.reduce((sum, item) => sum + item.file.size, 0),
        pages: items.reduce((sum, item) => sum + (item.pages ?? 0), 0),
      });
      const controller = new AbortController();
      task.current = controller;
      let timeout = false;
      const timer = setTimeout(() => {
        timeout = true;
        controller.abort();
      }, LIMITS.timeoutMs);
      setMessage("");
      setFailure("");
      setBusy("Combining PDFs…");
      try {
        const { bytes } = await processPdfs(
          "combine",
          items.map((i) => i.file),
          controller.signal,
          setBusy,
        );
        if (!bytes) throw new Error("No combined PDF was created.");
        if (held + bytes.byteLength > PHOTO_LIMITS.sessionBytes)
          throw new Error(photoCopy.budget);
        setBusy("Validating the result and preparing its preview…");
        const file = new File(
          [bytes as Uint8Array<ArrayBuffer>],
          safeFilename(name),
          { type: "application/pdf" },
        );
        const ok = await props.apply(file, controller.signal);
        if (controller.signal.aborted) throw new Error("Cancelled");
        if (!ok)
          throw new Error(
            "The combined PDF could not be previewed. Your previous document is unchanged.",
          );
        setMessage("");
        track("process_success", "combine", {
          fileCount: items.length,
          totalBytes: file.size,
          durationMs: performance.now() - started,
        });
        return true;
      } catch (error) {
        track(
          controller.signal.aborted && !timeout
            ? "process_cancel"
            : "process_failure",
          "combine",
          {
            durationMs: performance.now() - started,
            reason: analyticsReason(error, timeout),
          },
        );
        if (!controller.signal.aborted || timeout)
          setFailure(
            timeout
              ? "Processing took too long. Try fewer or smaller files."
              : error instanceof Error
                ? error.message
                : "Please try again.",
          );
        setMessage(
          timeout
            ? "Combining took too long. Try fewer or smaller PDFs. Your previous document is unchanged."
            : controller.signal.aborted
              ? "Cancelled. Your input list and previous document are unchanged."
              : error instanceof Error
                ? error.message
                : "Combining failed. Your previous document is unchanged.",
        );
        return false;
      } finally {
        clearTimeout(timer);
        task.current = null;
        setBusy("");
      }
    }
    return (
      <section
        className={`photo-task combine-task ${items.length ? "has-inputs" : "empty-inputs"}`}
        aria-label="Combine PDFs"
        onDragOver={(e) => {
          if (e.dataTransfer.types.includes("Files")) e.preventDefault();
        }}
        onDrop={(e) => {
          if (e.dataTransfer.files.length) {
            e.preventDefault();
            if (!task.current) void add(Array.from(e.dataTransfer.files));
          }
        }}
      >
        <h2>{items.length ? "Merge settings" : "Select PDFs to merge"}</h2>
        <p>Choose 2–10 PDFs, then arrange them in order.</p>
        <p className="limits">
          30 MiB input · 200 pages total · Originals unchanged
        </p>
        <FilePicker
          id="combine-files"

          accept=".pdf,application/pdf"
          multiple
          disabled={!!busy}
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            e.target.value = "";
            void add(files);
          }}
        >
          {items.length
            ? "Add more PDFs"
            : "Select PDF files or drop them here"}
        </FilePicker>
        <p className="input-status" aria-live="polite">
          {items.length} files · {pages} checked pages
          {items.some((i) => i.error) ? " · remove unsupported inputs" : ""}
        </p>
        {!items.length && (
          <details className="input-support">
            <summary>File support</summary>
            <p className="limits">
              Preserves supported links, bookmarks, page labels, comments,
              layers and tags. Complex signatures or incompatible structures are
              refused with a reason.
            </p>
          </details>
        )}
        <p className="limits session-estimate">
          Task input: {(held / 1048576).toFixed(1)} / 60 MiB. Estimated with
          output: {((held + estimate) / 1048576).toFixed(1)} MiB (conservative
          estimate; actual result is also checked).
        </p>
        {pages > 200 && (
          <p role="alert">
            Use at most 200 pages in total. Remove an input to continue.
          </p>
        )}
        {overBudget && <p role="alert">{photoCopy.budget}</p>}
        <ol className="photo-list" data-reorder-list>
          {items.map((item, index) => (
            <li key={item.id} data-sort-index={index}>
              <button
                className="merge-thumbnail secondary"
                disabled={!!busy || !item.thumbnail}
                aria-label={`Preview PDF ${index + 1}`}
                onClick={(e) => {
                  e.currentTarget.focus();
                  props.previewFile(item.file);
                }}
              >
                {item.thumbnail ? (
                  <img
                    draggable={false}
                    src={item.thumbnail}
                    alt={`First page of ${item.file.name}`}
                  />
                ) : (
                  <span>Preview unavailable</span>
                )}
              </button>
              <strong title={item.file.name}>
                <span className="file-index">{index + 1}.</span>
                <span className="file-name">{item.file.name}</span>
              </strong>
              <p>
                {(item.file.size / 1024).toFixed(1)} KiB · {item.pages ?? "?"}{" "}
                pages
              </p>
              {item.error && (
                <p role="alert">{item.error} Remove this input to continue.</p>
              )}
              <div className="photo-actions card-actions">
                <CardMove
                  index={index}
                  count={items.length}
                  label={`PDF ${index + 1}`}
                  disabled={!!busy}
                  move={(to) => move(item.id, to)}
                />
                <button
                  className="secondary"
                  disabled={!!busy}
                  aria-label={`Remove PDF ${index + 1}`}
                  onClick={() => {
                    setItems((old) => old.filter((i) => i.id !== item.id));
                    setDirty(true);
                  }}
                >
                  ×
                </button>
              </div>
            </li>
          ))}
        </ol>
        <details className="output-name">
          <summary>Output filename</summary>
          <label>
            Combined PDF name{" "}
            <input
              value={name}
              maxLength={180}
              disabled={!!busy}
              onChange={(e) => {
                setName(e.target.value);
                if (items.length > 1) setDirty(true);
              }}
            />
          </label>
        </details>
        {items.length === 1 && (
          <p className="task-guidance" role="status">
            Add one more PDF to merge your files.
          </p>
        )}
        {busy ? (
          <div role="status">
            <p>{busy}</p>
            <button onClick={() => task.current?.abort()}>
              Cancel combine task
            </button>
          </div>
        ) : (
          <div className="photo-actions">
            <button
              aria-label="Apply combine"
              disabled={!canApply}
              onClick={() => void apply()}
            >
              Merge PDF →
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
            message={busy || failure}
            close={() => {
              if (busy) task.current?.abort();
              else setFailure("");
            }}
          />
        )}
        {pending && (
          <LeaveTaskDialog
            description="Your selected PDFs and merge order will be cleared."
            keep={() => setPending(null)}
            leave={() => {
              const action = pending.action;
              setPending(null);
              setItems([]);
              setDirty(false);
              action();
            }}
          />
        )}
      </section>
    );
  },
);
