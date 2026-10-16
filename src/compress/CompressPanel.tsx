import { forwardRef, useImperativeHandle, useRef, useState } from "react";
import { LeaveTaskDialog } from "../LeaveTaskDialog";
import { LIMITS } from "../core/contracts";
import { safeFilename } from "../photos/model";
import { compressPdf } from "./service";
import {
  compressionOptions,
  summarizeCompression,
  type CompressionLevel,
  type CompressionSummary,
} from "./model";
import "./compress.css";
import { analyticsReason, track } from "../analytics";

export type CompressHandle = { guard: (action: () => void) => void };
type Props = {
  file: File;
  pages: number;
  apply: (
    file: File,
    summary: CompressionSummary,
    signal: AbortSignal,
  ) => Promise<boolean>;
  replace: () => void;
  onDirty: (value: boolean) => void;
  onBusy: (value: boolean) => void;
};

const size = (bytes: number) =>
  bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / 1024 / 1024).toFixed(1)} MB`;

export const CompressPanel = forwardRef<CompressHandle, Props>(
  function CompressPanel(
    { file, pages, apply, replace, onDirty, onBusy },
    ref,
  ) {
    const [level, setLevel] = useState<CompressionLevel>("recommended"),
      [stage, setStage] = useState(""),
      [message, setMessage] = useState(""),
      [leave, setLeave] = useState<(() => void) | null>(null);
    const job = useRef<AbortController | null>(null);
    const busy = !!stage;
    useImperativeHandle(ref, () => ({
      guard(action) {
        if (busy) return;
        setLeave(() => action);
      },
    }));
    function choose(value: CompressionLevel) {
      setLevel(value);
      setMessage("");
      onDirty(true);
    }
    async function run() {
      if (busy) return;
      const started = performance.now();
      track("process_start", "compress", {
        fileCount: 1,
        totalBytes: file.size,
        pages,
      });
      const controller = new AbortController();
      let timedOut = false;
      const timer = window.setTimeout(() => {
        timedOut = true;
        controller.abort();
      }, LIMITS.timeoutMs);
      job.current = controller;
      onBusy(true);
      setMessage("");
      try {
        const candidate = await compressPdf(
          file,
          level,
          controller.signal,
          setStage,
        );
        if (controller.signal.aborted)
          throw new DOMException("Aborted", "AbortError");
        setStage("Verifying the smaller PDF…");
        const summary = summarizeCompression(
          file.size,
          candidate.byteLength,
          level,
        );
        const bytes = summary.alreadyOptimized
          ? new Uint8Array(await file.arrayBuffer())
          : candidate;
        const output = new File(
          [bytes as Uint8Array<ArrayBuffer>],
          safeFilename(file.name.replace(/\.pdf$/i, "") + "-compressed.pdf"),
          { type: "application/pdf" },
        );
        const applied = await apply(output, summary, controller.signal);
        if (controller.signal.aborted)
          throw new DOMException("Aborted", "AbortError");
        if (!applied)
          throw new Error(
            "The compressed result could not be verified. Your original is unchanged.",
          );
        track("process_success", "compress", {
          fileCount: 1,
          totalBytes: output.size,
          pages,
          durationMs: performance.now() - started,
        });
      } catch (error) {
        track(
          controller.signal.aborted && !timedOut
            ? "process_cancel"
            : "process_failure",
          "compress",
          {
            durationMs: performance.now() - started,
            reason: analyticsReason(error, timedOut),
          },
        );
        if (timedOut)
          setMessage(
            "Compression took too long. Try a smaller PDF or Highest quality. Your original is unchanged.",
          );
        else if (!controller.signal.aborted)
          setMessage(
            error instanceof Error
              ? error.message
              : "Compression could not finish. Your original is unchanged.",
          );
      } finally {
        window.clearTimeout(timer);
        if (job.current === controller) {
          job.current = null;
          setStage("");
          onBusy(false);
        }
      }
    }
    return (
      <section className="compress-task">
        <div className="compress-source">
          <div className="compress-file-icon" aria-hidden="true">
            PDF
          </div>
          <div>
            <strong title={file.name}>{file.name}</strong>
            <span>
              {pages} {pages === 1 ? "page" : "pages"} · {size(file.size)}
            </span>
          </div>
          <button className="secondary" disabled={busy} onClick={replace}>
            Replace
          </button>
        </div>
        <fieldset className="compression-levels">
          <legend>Choose compression level</legend>
          {compressionOptions.map((option) => (
            <label
              key={option.value}
              className={level === option.value ? "selected" : ""}
            >
              <input
                type="radio"
                name="compression-level"
                value={option.value}
                checked={level === option.value}
                disabled={busy}
                onChange={() => choose(option.value)}
              />
              <span className="compression-copy">
                <span className="compression-title">
                  <strong>{option.title}</strong>
                  {option.badge && <small>{option.badge}</small>}
                </span>
                <span>{option.description}</span>
                <small>{option.detail}</small>
              </span>
            </label>
          ))}
        </fieldset>
        <details className="compression-details">
          <summary>What will change?</summary>
          <p>
            Text, vectors, page sizes, links, bookmarks, page labels and
            supported forms stay editable. The recommended and smaller settings
            may recompress suitable images. Unsupported image structures stay
            unchanged.
          </p>
          <p>
            This tool does not rasterize whole pages or silently remove
            metadata. Exact output size is not guaranteed. A larger candidate is
            discarded.
          </p>
        </details>
        <div className="compress-actions">
          <button disabled={busy} onClick={() => void run()}>
            Compress PDF
          </button>
          <button
            className="secondary"
            disabled={busy}
            onClick={() => setLeave(() => replace)}
          >
            Cancel task
          </button>
        </div>
        {!!message && (
          <p className="message" role="alert">
            {message}
          </p>
        )}
        {!!stage && (
          <div className="busy compress-progress" role="status">
            <h2>Compressing your PDF…</h2>
            <progress aria-label="Compression in progress" />
            <p>{stage}</p>
            <button className="secondary" onClick={() => job.current?.abort()}>
              Cancel processing
            </button>
          </div>
        )}
        {leave && (
          <LeaveTaskDialog
            description="This PDF and your compression setting will be cleared."
            keep={() => setLeave(null)}
            leave={() => {
              const action = leave;
              setLeave(null);
              onDirty(false);
              action();
            }}
          />
        )}
      </section>
    );
  },
);
