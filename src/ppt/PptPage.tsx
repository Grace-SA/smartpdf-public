import { useEffect, useRef, useState } from "react";
import { FilePicker } from "../FilePicker";
import { FilePreview } from "../FilePreview";
import type { Engine } from "../platform/engine";
import { ToolNavigation } from "../ToolNavigation";
import { toolPaths } from "../routes";
import { LeaveTaskDialog } from "../LeaveTaskDialog";
import { SeoContent, applySeo } from "../SeoContent";
import { checkPptLocally } from "./preflight";
import { wordRequest as request } from "../word/errors";
import "../word/word.css";

type Job = {
  id: string;
  state: string;
  pages?: number;
  warnings: string[];
  error?: string;
  cleanupPending?: boolean;
};
type Service = {
  available: boolean;
  region: string;
  retentionMinutes: number;
  mode?: string;
};
const mime =
  "application/vnd.openxmlformats-officedocument.presentationml.presentation";
const stages: Record<string, string> = {
  created: "Ready to upload",
  uploading: "Uploading presentation…",
  queued: "Waiting for conversion…",
  checking: "Checking presentation…",
  starting: "Preparing conversion…",
  converting: "Converting slides to PDF…",
  "checking-result": "Checking the PDF…",
};
const pause = (signal: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const abort = () => {
      clearTimeout(timer);
      reject(new DOMException("Cancelled", "AbortError"));
    };
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", abort);
      resolve();
    }, 500);
    if (signal.aborted) abort();
    else signal.addEventListener("abort", abort, { once: true });
  });

export function PptPage() {
  const [service, setService] = useState<Service>();
  const [file, setFile] = useState<File>();
  const [checked, setChecked] = useState(false);
  const [checking, setChecking] = useState(false);
  const [job, setJob] = useState<Job>();
  const [busy, setBusy] = useState(false);
  const [cleanup, setCleanup] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<File>();
  const [url, setUrl] = useState("");
  const [progress, setProgress] = useState<number>();
  const [preview, setPreview] = useState<Engine>();
  const [opening, setOpening] = useState(false);
  const [destination, setDestination] = useState("");
  const current = useRef<string | undefined>(undefined);
  const controller = useRef<AbortController | null>(null);
  const checker = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  const alert = useRef<HTMLParagraphElement>(null);
  const complete = useRef<HTMLHeadingElement>(null);

  async function connect() {
    try {
      const next = await request<Service>("/api/ppt/session");
      if (mounted.current) {
        setService(next);
        setError("");
      }
    } catch {
      if (mounted.current)
        setError(
          "Conversion is unavailable. Retry connection; your presentation has not been uploaded.",
        );
    }
  }
  useEffect(() => {
    applySeo("ppt");
    mounted.current = true;
    const discard = () => {
      checker.current?.abort();
      controller.current?.abort();
      if (current.current)
        void fetch(`/api/ppt/jobs/${current.current}`, {
          method: "DELETE",
          keepalive: true,
        }).catch(() => {});
    };
    const restore = (event: PageTransitionEvent) => {
      if (event.persisted) location.reload();
    };
    void request<Service>("/api/ppt/session")
      .then((value) => {
        if (mounted.current) setService(value);
      })
      .catch(() => {
        if (mounted.current)
          setError(
            "Conversion is unavailable. Retry connection; your presentation has not been uploaded.",
          );
      });
    window.addEventListener("pagehide", discard);
    window.addEventListener("pageshow", restore);
    return () => {
      mounted.current = false;
      discard();
      window.removeEventListener("pagehide", discard);
      window.removeEventListener("pageshow", restore);
    };
  }, []);
  useEffect(
    () => () => {
      if (url) URL.revokeObjectURL(url);
    },
    [url],
  );
  useEffect(() => () => preview?.dispose(), [preview]);
  useEffect(() => {
    if (error) alert.current?.focus();
  }, [error]);
  useEffect(() => {
    if (result) complete.current?.focus();
  }, [result]);

  async function choose(files: File[]) {
    if (busy || current.current || cleanup || !files.length) return;
    checker.current?.abort();
    setFile(undefined);
    setChecked(false);
    setError("");
    setChecking(false);
    const next = files[0]!;
    if (
      files.length !== 1 ||
      !/\.pptx$/i.test(next.name) ||
      !next.size ||
      next.size > 60 * 1024 ** 2
    ) {
      setError(
        "Choose one PPTX up to 60 MiB. Older PPT files are not supported yet.",
      );
      return;
    }
    setFile(next);
    setChecking(true);
    const abort = new AbortController();
    checker.current = abort;
    try {
      // Keep the checked bytes stable even after the native picker resets or
      // the source on disk changes. The same immutable snapshot is uploaded.
      const snapshot = new File([await next.arrayBuffer()], next.name, {
        type: next.type,
        lastModified: next.lastModified,
      });
      if (abort.signal.aborted || !mounted.current) return;
      setFile(snapshot);
      await checkPptLocally(snapshot, abort.signal);
      if (!abort.signal.aborted && mounted.current) setChecked(true);
    } catch (cause) {
      if (!abort.signal.aborted && mounted.current)
        setError(
          cause instanceof Error ? cause.message : "Choose a valid PPTX.",
        );
    } finally {
      if (!abort.signal.aborted && mounted.current) setChecking(false);
    }
  }

  async function remove() {
    controller.current?.abort();
    controller.current = null;
    setBusy(true);
    setCleanup(true);
    setError("");
    setPreview(undefined);
    setResult(undefined);
    setUrl("");
    try {
      if (current.current) {
        let deleted = await request<Job>(`/api/ppt/jobs/${current.current}`, {
          method: "DELETE",
        });
        const until = Date.now() + 30000;
        while (deleted.cleanupPending && Date.now() < until) {
          await new Promise((resolve) => setTimeout(resolve, 500));
          deleted = await request<Job>(`/api/ppt/jobs/${current.current}`);
        }
        if (deleted.cleanupPending)
          throw Error(
            "Temporary-file cleanup could not be confirmed. Retry deletion.",
          );
      }
      if (mounted.current) {
        current.current = undefined;
        setCleanup(false);
        setJob(undefined);
        setFile(undefined);
        setChecked(false);
      }
      return true;
    } catch {
      if (mounted.current)
        setError(
          "Temporary-file cleanup could not be confirmed. Retry deletion before another conversion.",
        );
      return false;
    } finally {
      if (mounted.current) {
        setBusy(false);
        setProgress(undefined);
      }
    }
  }

  async function start() {
    if (
      !file ||
      !checked ||
      busy ||
      cleanup ||
      current.current ||
      !service?.available
    )
      return;
    const input = file;
    const abort = new AbortController();
    controller.current = abort;
    setBusy(true);
    setError("");
    let id: string | undefined;
    try {
      const created = await request<Job>("/api/ppt/jobs", {
        method: "POST",
        signal: abort.signal,
      });
      id = created.id;
      current.current = id;
      if (abort.signal.aborted) return;
      setJob({ ...created, state: "uploading" });
      await new Promise<void>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("PUT", `/api/ppt/jobs/${id}/input`);
        xhr.setRequestHeader("Content-Type", mime);
        xhr.timeout = 125000;
        const cancel = () => xhr.abort();
        abort.signal.addEventListener("abort", cancel, { once: true });
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable && !abort.signal.aborted)
            setProgress(Math.floor((event.loaded / event.total) * 100));
        };
        xhr.onloadend = () => abort.signal.removeEventListener("abort", cancel);
        xhr.onload = () => {
          if (xhr.status === 202) resolve();
          else reject(Error("Upload failed. Retry or choose a smaller PPTX."));
        };
        xhr.onerror = xhr.ontimeout = () =>
          reject(Error("Upload interrupted. Check your connection and retry."));
        xhr.onabort = () => reject(new DOMException("Cancelled", "AbortError"));
        if (abort.signal.aborted)
          reject(new DOMException("Cancelled", "AbortError"));
        else xhr.send(input);
      });
      setProgress(undefined);
      const until = Date.now() + 16 * 60000;
      while (!abort.signal.aborted) {
        if (Date.now() > until)
          throw Error(
            "Conversion took too long. Retry or export from PowerPoint.",
          );
        const next = await request<Job>(`/api/ppt/jobs/${id}`, {
          signal: abort.signal,
        });
        if (abort.signal.aborted || !mounted.current) return;
        setJob(next);
        if (["failed", "cancelled", "expired"].includes(next.state))
          throw Error(
            next.error ||
              "This conversion is unavailable. Choose the presentation again.",
          );
        if (next.state === "succeeded") {
          const response = await fetch(`/api/ppt/jobs/${id}/result`, {
            signal: abort.signal,
          });
          if (!response.ok)
            throw Error("The result is unavailable. Retry conversion.");
          const bytes = await response.blob();
          if (
            bytes.size > 30 * 1024 ** 2 ||
            (await bytes.slice(0, 5).text()) !== "%PDF-"
          )
            throw Error("The PDF failed its checks.");
          if (abort.signal.aborted || !mounted.current) return;
          const pdf = new File(
            [bytes],
            input.name.replace(/\.pptx$/i, ".pdf"),
            { type: "application/pdf" },
          );
          setResult(pdf);
          setUrl(URL.createObjectURL(pdf));
          break;
        }
        await pause(abort.signal);
      }
    } catch (cause) {
      if (!abort.signal.aborted && mounted.current) {
        setError(cause instanceof Error ? cause.message : "Conversion failed.");
        if (id) setCleanup(true);
      }
    } finally {
      if (mounted.current && controller.current === abort) {
        setBusy(false);
        setProgress(undefined);
      }
    }
  }

  async function showPreview() {
    const expected = current.current;
    setOpening(true);
    try {
      const { Engine } = await import("../platform/engine");
      const engine = new Engine();
      try {
        await engine.prepare(controller.current?.signal);
      } catch (cause) {
        engine.dispose();
        throw cause;
      }
      if (
        mounted.current &&
        current.current === expected &&
        !controller.current?.signal.aborted
      )
        setPreview(engine);
      else engine.dispose();
    } catch {
      if (mounted.current && current.current === expected)
        setError(
          "Preview could not load. You can still download and check the PDF.",
        );
    } finally {
      if (mounted.current) setOpening(false);
    }
  }
  function navigate(href: string) {
    if (file || current.current) setDestination(href);
    else location.assign(href);
  }
  return (
    <div
      className="product-app word-app"
      data-screen="task"
      onClickCapture={(event) => {
        const anchor =
          event.target instanceof Element
            ? event.target.closest("a[href]")
            : null;
        if (
          anchor instanceof HTMLAnchorElement &&
          !anchor.hasAttribute("download") &&
          anchor.origin === location.origin &&
          !event.metaKey &&
          !event.ctrlKey &&
          !event.shiftKey &&
          event.button === 0 &&
          (file || job?.id)
        ) {
          event.preventDefault();
          navigate(anchor.href);
        }
      }}
    >
      <header>
        <a className="brand" href="/" aria-label="Smart PDF home">
          <span className="brand-mark">S</span>
          <span className="brand-wordmark">
            Smart<strong>PDF</strong>
          </span>
        </a>
        <ToolNavigation
          active="ppt"
          keepCurrent
          disabled={busy}
          choose={(tool) => navigate(toolPaths[tool])}
        />
        <span className="version">
          {service?.mode === "local" ? "Local conversion" : "Cloud conversion"}
        </span>
      </header>
      <main className="word-page">
        <div className="task-heading">
          <a className="secondary" href="/">
            ← All tools
          </a>
          <div>
            <h1>PowerPoint to PDF</h1>
            <p>Keep your slide size. One visible slide per PDF page.</p>
          </div>
        </div>
        <section
          className="word-card"
          aria-label="PowerPoint to PDF conversion"
          onDragOver={(event) => {
            event.preventDefault();
            event.dataTransfer.dropEffect = busy || job?.id ? "none" : "copy";
          }}
          onDrop={(event) => {
            event.preventDefault();
            void choose(Array.from(event.dataTransfer.files));
          }}
        >
          {!result && (
            <div className={file ? "word-selected" : "word-dropzone"}>
              <div className="word-selection-copy">
                {file ? (
                  <>
                    <p className="word-filename">
                      {file.name} · {(file.size / 1024).toFixed(1)} KiB
                    </p>
                    <p>
                      {job?.id
                        ? "Your original stays on this device"
                        : "Selected on this device · not uploaded yet"}
                    </p>
                  </>
                ) : (
                  <>
                    <h2>Drop your PowerPoint presentation here</h2>
                    <p>or choose a file from your device</p>
                  </>
                )}
              </div>
              <FilePicker
                id="ppt-file"
                accept={`.pptx,${mime}`}
                disabled={busy || !!job?.id || cleanup}
                onChange={(event) => {
                  const input = event.currentTarget;
                  const files = Array.from(input.files || []);
                  void choose(files).finally(() => {
                    if (input.files?.[0] === files[0]) input.value = "";
                  });
                }}
              >
                {file ? "Change presentation" : "Select PowerPoint file"}
              </FilePicker>
              {!file && (
                <p className="limits">
                  One PPTX · up to 60 MiB · up to 200 visible slides
                </p>
              )}
            </div>
          )}
          {file && !job?.id && (
            <p role="status">
              {checking
                ? "Checking presentation on this device… Nothing is being uploaded."
                : checked
                  ? "Basic file checks passed. Slides and resources are checked again during conversion."
                  : "Choose a corrected PPTX to continue."}
            </p>
          )}
          {!result && (
            <div className="word-cloud-note">
              <strong>
                {service?.mode === "local"
                  ? "Conversion on this computer"
                  : "Cloud conversion"}
                {service ? ` · ${service.region}` : ""}
              </strong>
              <p>
                Your presentation is uploaded only when you choose Upload and
                convert.{" "}
                {service
                  ? `Temporary files expire within ${service.retentionMinutes} minutes; you can delete them sooner.`
                  : "Connect to see processing details."}
              </p>
              <p>
                Hidden slides, speaker notes and comments are excluded.
                Animations become static. Fonts and complex graphics may change.
              </p>
            </div>
          )}
          {busy && (
            <p role="status" aria-live="polite">
              {cleanup
                ? "Deleting temporary files…"
                : progress !== undefined
                  ? `Uploading presentation… ${progress}%`
                  : stages[job?.state || "created"] || "Preparing conversion…"}
            </p>
          )}
          {error && (
            <p className="word-error" role="alert" tabIndex={-1} ref={alert}>
              {error}
            </p>
          )}
          {result && (
            <div className="word-result">
              <h2 tabIndex={-1} ref={complete}>
                Your PDF is ready
              </h2>
              <p className="word-filename">{result.name}</p>
              <p>{job?.pages} pages · original slide size</p>
              <p className="limits">
                {service?.region} · temporary files expire within{" "}
                {service?.retentionMinutes} minutes
              </p>
              <div className="word-actions">
                <a className="word-download" href={url} download={result.name}>
                  Download PDF
                </a>
                <button
                  className="secondary"
                  disabled={opening}
                  onClick={() => void showPreview()}
                >
                  {opening ? "Opening preview…" : "Preview PDF"}
                </button>
              </div>
              {job?.warnings?.map((warning) => (
                <p key={warning}>{warning}</p>
              ))}
            </div>
          )}
          <div className="word-actions">
            {file && !job?.id && !busy && !result && (
              <button
                className="word-convert"
                disabled={
                  !checked || !service?.available || checking || cleanup
                }
                onClick={() => void start()}
              >
                Upload and convert
              </button>
            )}
            {busy && !cleanup && (
              <button className="secondary" onClick={() => void remove()}>
                Cancel conversion
              </button>
            )}
            {!busy && !!job?.id && (
              <button className="secondary" onClick={() => void remove()}>
                {cleanup
                  ? "Retry deletion"
                  : result
                    ? "Delete files and convert another"
                    : "Delete temporary files"}
              </button>
            )}
            {!service?.available && !busy && (
              <button className="secondary" onClick={() => void connect()}>
                Retry connection
              </button>
            )}
          </div>
          <details className="input-support">
            <summary>Supported presentations</summary>
            <p>
              Standard PPTX with text, shapes, tables, embedded PNG/JPEG
              pictures and common charts. Check fonts, diagrams and complex
              layouts in the PDF. Older PPT, passwords, macros, embedded
              media/fonts, active objects and externally linked resources are
              not supported. Your original stays unchanged.
            </p>
          </details>
        </section>
        <SeoContent tool="ppt" />
        <footer className="site-footer">
          <a href="/privacy/">Privacy and file handling</a>
          <a href="/notices/index.html">Third-party notices</a>
        </footer>
      </main>
      {preview && result && (
        <FilePreview
          file={result}
          engine={preview}
          close={() => setPreview(undefined)}
        />
      )}
      {destination && (
        <LeaveTaskDialog
          description="Leaving requests deletion of temporary conversion files. Download your PDF first if you want to keep it."
          keep={() => setDestination("")}
          leave={() => {
            const target = destination;
            void remove().then((removed) => {
              if (removed) location.assign(target);
            });
          }}
        />
      )}
    </div>
  );
}
