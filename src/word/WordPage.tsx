import { useEffect, useRef, useState } from "react";
import { FilePicker } from "../FilePicker";
import { FilePreview } from "../FilePreview";
import type { Engine } from "../platform/engine";
import { SeoContent, applySeo } from "../SeoContent";
import { ToolNavigation } from "../ToolNavigation";
import { toolPaths } from "../routes";
import { LeaveTaskDialog } from "../LeaveTaskDialog";
import "./word.css";
import { checkWordLocally } from "./preflight-service";
import type { WordCheck } from "./preflight-core";

type Job = {
  id: string;
  state: string;
  pages?: number;
  warnings: string[];
  error?: string;
  cleanupPending?: boolean;
};
type Service = { region: string; available: boolean; retentionMinutes: number };
const stages: Record<string, string> = {
  created: "Ready to upload",
  uploading: "Uploading document…",
  queued: "Waiting for conversion…",
  checking: "Checking document…",
  starting: "Preparing your conversion…",
  converting: "Converting to PDF…",
  "checking-result": "Checking the PDF…",
};
async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { credentials: "same-origin", ...init });
  const value = await response.json();
  if (!response.ok)
    throw new Error(
      value.error ||
        "The conversion service is unavailable. Try again shortly.",
    );
  return value as T;
}
export function WordPage() {
  const [service, setService] = useState<Service>();
  const [file, setFile] = useState<File>();
  const [job, setJob] = useState<Job>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState<number>();
  const [result, setResult] = useState<File>();
  const [url, setUrl] = useState("");
  const [preview, setPreview] = useState<Engine>();
  const [opening, setOpening] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [connecting, setConnecting] = useState(true);
  const [localCheck, setLocalCheck] = useState<WordCheck>();
  const [checkingLocal, setCheckingLocal] = useState(false);
  const checkController = useRef<AbortController | null>(null);
  const [destination, setDestination] = useState("");
  const leaving = useRef(false);
  const controller = useRef<AbortController | null>(null);
  const currentJob = useRef<string | undefined>(undefined);
  const mounted = useRef(true);
  async function connect() {
    setConnecting(true);
    try {
      const value = await request<Service>("/api/word/session");
      if (mounted.current) {
        setService(value);
        setError("");
      }
    } catch {
      setError(
        "Cloud conversion is unavailable. Retry connecting; your document has not been uploaded.",
      );
    } finally {
      if (mounted.current) setConnecting(false);
    }
  }
  useEffect(() => {
    applySeo("word");
    mounted.current = true;
    const discard = () => {
      checkController.current?.abort();
      controller.current?.abort();
      if (currentJob.current)
        void fetch(`/api/word/jobs/${currentJob.current}`, {
          method: "DELETE",
          keepalive: true,
        });
    };
    const restore = (event: PageTransitionEvent) => {
      if (event.persisted) {
        leaving.current = true;
        location.reload();
      }
    };
    window.addEventListener("pagehide", discard);
    window.addEventListener("pageshow", restore);
    void request<Service>("/api/word/session")
      .then((value) => {
        if (mounted.current) setService(value);
      })
      .catch(() => {
        if (mounted.current)
          setError(
            "Cloud conversion is unavailable. Retry connecting; your document has not been uploaded.",
          );
      })
      .finally(() => {
        if (mounted.current) setConnecting(false);
      });
    return () => {
      mounted.current = false;
      window.removeEventListener("pagehide", discard);
      window.removeEventListener("pageshow", restore);
      discard();
    };
  }, []);
  useEffect(
    () => () => {
      if (url) URL.revokeObjectURL(url);
    },
    [url],
  );
  useEffect(() => {
    const before = (event: BeforeUnloadEvent) => {
      if (!leaving.current && (busy || file || result)) event.preventDefault();
    };
    window.addEventListener("beforeunload", before);
    return () => window.removeEventListener("beforeunload", before);
  }, [busy, file, result]);
  useEffect(() => () => preview?.dispose(), [preview]);
  function navigate(target: string) {
    if (file || busy || result) setDestination(target);
    else location.assign(target);
  }
  function leave() {
    leaving.current = true;
    controller.current?.abort();
    if (currentJob.current)
      void fetch(`/api/word/jobs/${currentJob.current}`, {
        method: "DELETE",
        keepalive: true,
      });
    location.assign(destination);
  }
  function choose(files: File[]) {
    checkController.current?.abort();
    setLocalCheck(undefined);
    setCheckingLocal(false);
    setError("");
    setFile(undefined);
    if (files.length !== 1 || !/\.docx$/i.test(files[0]?.name || "")) {
      setError(
        "Choose one DOCX document. Save older .doc files as .docx in Word first.",
      );
      return;
    }
    if (!files[0]!.size || files[0]!.size > 30 * 1024 ** 2) {
      setError("Choose a non-empty DOCX up to 30 MiB.");
      return;
    }
    setFile(files[0]);
    setJob(undefined);
    setResult(undefined);
    setUrl("");
    const check = new AbortController();
    checkController.current = check;
    setCheckingLocal(true);
    void checkWordLocally(files[0]!, check.signal)
      .then((value) => {
        if (mounted.current && !check.signal.aborted) setLocalCheck(value);
      })
      .catch((cause) => {
        if (mounted.current && !check.signal.aborted)
          setError(
            cause instanceof Error
              ? cause.message
              : "Local checking failed. Choose the document again.",
          );
      })
      .finally(() => {
        if (mounted.current && !check.signal.aborted) setCheckingLocal(false);
      });
  }
  async function start() {
    if (
      !file ||
      busy ||
      checkingLocal ||
      !localCheck ||
      localCheck.issues.length
    )
      return;
    const abort = new AbortController();
    controller.current = abort;
    setBusy(true);
    setError("");
    setProgress(undefined);
    setResult(undefined);
    let id: string | undefined;
    try {
      const created = await request<Job>("/api/word/jobs", {
        method: "POST",
        signal: abort.signal,
      });
      id = created.id;
      currentJob.current = id;
      if (abort.signal.aborted)
        throw new DOMException("Cancelled", "AbortError");
      setJob({ ...created, state: "uploading" });
      await new Promise<void>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("PUT", `/api/word/jobs/${id}/input`);
        xhr.setRequestHeader(
          "Content-Type",
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        );
        xhr.timeout = 135000;
        const cancelUpload = () => xhr.abort();
        abort.signal.addEventListener("abort", cancelUpload, { once: true });
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable)
            setProgress(Math.floor((event.loaded / event.total) * 100));
        };
        xhr.onloadend = () =>
          abort.signal.removeEventListener("abort", cancelUpload);
        xhr.onload = () =>
          xhr.status === 202
            ? resolve()
            : reject(
                new Error(
                  "Upload could not finish. Retry with a DOCX up to 30 MiB.",
                ),
              );
        xhr.onerror = xhr.ontimeout = () =>
          reject(
            new Error(
              "Upload could not finish. Check your connection and retry.",
            ),
          );
        xhr.onabort = () => reject(new DOMException("Cancelled", "AbortError"));
        xhr.send(file);
      });
      setProgress(undefined);
      const deadline = Date.now() + 16 * 60000;
      while (!abort.signal.aborted) {
        if (Date.now() > deadline)
          throw new Error(
            "Conversion took too long. Retry or export from Word.",
          );
        const next = await request<Job>(`/api/word/jobs/${id}`, {
          signal: abort.signal,
        });
        if (!mounted.current) return;
        setJob(next);
        if (["failed", "expired", "cancelled"].includes(next.state))
          throw new Error(
            next.error ||
              "This conversion was cancelled or expired. Choose the document again.",
          );
        if (next.state === "succeeded") {
          const response = await fetch(`/api/word/jobs/${id}/result`, {
            signal: abort.signal,
          });
          if (!response.ok)
            throw new Error(
              "The PDF could not be downloaded. Retry the conversion.",
            );
          const blob = await response.blob();
          if (
            blob.size > 30 * 1024 ** 2 ||
            !(await blob.slice(0, 5).text()).startsWith("%PDF-")
          )
            throw new Error("The result is not a valid PDF.");
          const pdf = new File([blob], file.name.replace(/\.docx$/i, ".pdf"), {
            type: "application/pdf",
          });
          setResult(pdf);
          setUrl(URL.createObjectURL(pdf));
          break;
        }
        await new Promise<void>((resolve, reject) => {
          const cancelWait = () => {
            clearTimeout(timer);
            reject(new DOMException("Cancelled", "AbortError"));
          };
          const timer = setTimeout(() => {
            abort.signal.removeEventListener("abort", cancelWait);
            resolve();
          }, 1000);
          abort.signal.addEventListener("abort", cancelWait, { once: true });
        });
      }
    } catch (cause) {
      if (mounted.current && !abort.signal.aborted)
        setError(
          cause instanceof Error
            ? cause.message
            : "Conversion failed. Try again.",
        );
      if (id)
        void fetch(`/api/word/jobs/${id}`, {
          method: "DELETE",
          keepalive: true,
        });
    } finally {
      if (mounted.current && controller.current === abort) {
        setBusy(false);
        setProgress(undefined);
      }
    }
  }
  async function remove() {
    const active = controller.current;
    controller.current = null;
    active?.abort();
    const id = currentJob.current;
    setBusy(true);
    setError("");
    setPreview(undefined);
    setResult(undefined);
    setUrl("");
    try {
      if (id) {
        let next = await request<Job>(`/api/word/jobs/${id}`, {
          method: "DELETE",
        });
        setJob(next);
        const deadline = Date.now() + 30000;
        while (next.cleanupPending && Date.now() < deadline) {
          await new Promise((resolve) => setTimeout(resolve, 500));
          next = await request<Job>(`/api/word/jobs/${id}`);
          setJob(next);
        }
        if (next.cleanupPending)
          throw new Error(
            "Access has been removed. Server cleanup is still in progress; retry deletion shortly.",
          );
      }
      currentJob.current = undefined;
      setFile(undefined);
      setLocalCheck(undefined);
      setJob({ id: "", state: "deleted", warnings: [] });
    } catch {
      setError(
        "Access removal or server cleanup could not be confirmed. Retry deletion; temporary files expire within one hour.",
      );
    } finally {
      if (mounted.current) setBusy(false);
    }
  }
  async function showPreview() {
    setOpening(true);
    setError("");
    const signal = controller.current?.signal;
    const expectedJob = currentJob.current;
    try {
      const { Engine } = await import("../platform/engine");
      const engine = new Engine();
      await engine.prepare(signal);
      if (
        mounted.current &&
        !signal?.aborted &&
        currentJob.current === expectedJob
      )
        setPreview(engine);
      else engine.dispose();
    } catch {
      if (mounted.current && !signal?.aborted)
        setError(
          "Preview could not load. You can still download the PDF and check it before sharing.",
        );
    } finally {
      if (mounted.current) setOpening(false);
    }
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
          ["http:", "https:"].includes(anchor.protocol) &&
          !event.metaKey &&
          !event.ctrlKey &&
          !event.shiftKey &&
          !event.altKey &&
          event.button === 0 &&
          anchor.origin === location.origin &&
          (file || busy || result)
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
          active="word"
          keepCurrent
          disabled={busy}
          choose={(tool) => navigate(toolPaths[tool])}
        />
        <span className="version">Cloud conversion</span>
      </header>
      <main className="word-page">
        <div className="task-heading">
          <a className="secondary" href="/">
            ← All tools
          </a>
          <div>
            <h1>Word to PDF</h1>
            <p>Convert one DOCX, then check and download your PDF.</p>
          </div>
        </div>
        <section
          className={`word-card${dragging ? " is-dragging" : ""}`}
          aria-label="Word to PDF conversion"
          onDragOver={(event) => {
            event.preventDefault();
            event.dataTransfer.dropEffect = busy || result ? "none" : "copy";
            if (!busy && !result) setDragging(true);
          }}
          onDragLeave={(event) => {
            if (
              !event.currentTarget.contains(event.relatedTarget as Node | null)
            )
              setDragging(false);
          }}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            if (!busy && !result) choose(Array.from(event.dataTransfer.files));
          }}
        >
          {!result && (
            <div className={file ? "word-selected" : "word-dropzone"}>
              <svg
                className="word-document-icon"
                viewBox="0 0 48 56"
                fill="none"
                aria-hidden="true"
              >
                <path
                  d="M9 2h21l15 15v34a3 3 0 0 1-3 3H9a3 3 0 0 1-3-3V5a3 3 0 0 1 3-3Z"
                  fill="currentColor"
                  fillOpacity=".08"
                  stroke="currentColor"
                  strokeWidth="2"
                />
                <path
                  d="M30 2v15h15M15 28l3 12 4-9 4 9 3-12M33 29h5M33 35h5M15 46h23"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <div className="word-selection-copy">
                {file ? (
                  <>
                    <p className="word-filename">
                      {file.name} · {(file.size / 1024).toFixed(1)} KiB
                    </p>
                    <p className="word-local-status">
                      {busy || job?.id
                        ? "Your original stays on this device"
                        : "Selected on this device · not uploaded yet"}
                    </p>
                  </>
                ) : (
                  <>
                    <h2>
                      {dragging
                        ? "Drop your document to select it"
                        : "Drop your Word document here"}
                    </h2>
                    <p>or choose a file from your device</p>
                  </>
                )}
              </div>
              <FilePicker
                id="word-file"
                accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                disabled={busy}
                onChange={(event) => {
                  const files = Array.from(event.target.files || []);
                  event.target.value = "";
                  if (files.length) choose(files);
                }}
              >
                {file ? "Change document" : "Choose a Word document"}
              </FilePicker>
              {!file && (
                <p className="limits">
                  One DOCX · up to 30 MiB · up to 200 output pages
                </p>
              )}
            </div>
          )}
          {file && !result && !busy && (
            <div className="word-local-check" aria-live="polite">
              {checkingLocal ? (
                <p role="status">
                  Checking this document on your device… Nothing is being
                  uploaded.
                </p>
              ) : localCheck ? (
                <>
                  <strong>
                    {localCheck.issues.length
                      ? "This document needs attention"
                      : "Local checks passed"}
                  </strong>
                  {localCheck.issues.length > 0 && (
                    <ul role="alert">
                      {localCheck.issues.map((issue) => (
                        <li key={issue.code}>{issue.message}</li>
                      ))}
                    </ul>
                  )}
                  {!localCheck.issues.length && (
                    <p>
                      Your document is still on this device. The server will
                      verify it again after you choose Upload and convert.
                    </p>
                  )}
                </>
              ) : null}
            </div>
          )}
          <div className="word-cloud-note" role="note">
            <strong>Cloud conversion</strong>
            <p>
              Your document is uploaded only when you choose Upload and convert.
              Processing:{" "}
              {service?.region ||
                (connecting
                  ? "checking server availability…"
                  : "connection unavailable")}
              . Temporary files are kept for at most one hour. You can delete
              them sooner.
            </p>
          </div>
          {busy && (
            <div role="status" aria-live="polite">
              <p>
                {job?.state === "cancelled"
                  ? "Removing temporary files…"
                  : stages[job?.state || "created"] || "Connecting…"}
              </p>
              <p>This can take a few minutes. You can cancel at any time.</p>
              {progress !== undefined && (
                <>
                  <progress
                    max="100"
                    value={progress}
                    aria-label="Upload progress"
                  />
                  <span> {progress}% uploaded</span>
                </>
              )}
            </div>
          )}
          {error && (
            <p role="alert" className="word-error">
              {error}
            </p>
          )}
          {job?.state === "deleted" && (
            <p role="status">
              Temporary files deleted. Your original is unchanged.
            </p>
          )}
          {result && (
            <div className="word-result">
              <h2>Your PDF is ready</h2>
              <p>
                {job?.pages} {job?.pages === 1 ? "page" : "pages"} · Check the
                layout before sharing.
              </p>
              <ul>
                {job?.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
              <div className="word-actions">
                <button
                  className="secondary"
                  onClick={() => void showPreview()}
                  disabled={opening}
                >
                  {opening ? "Opening preview…" : "Preview PDF"}
                </button>
                <a className="word-download" href={url} download={result.name}>
                  Download PDF
                </a>
              </div>
            </div>
          )}
          <div className="word-actions">
            {file && !result && !busy && (
              <button
                className="word-convert"
                onClick={() => void start()}
                disabled={
                  !file ||
                  !service?.available ||
                  checkingLocal ||
                  !localCheck ||
                  localCheck.issues.length > 0
                }
              >
                Upload and convert
              </button>
            )}
            {busy && job?.state !== "cancelled" && (
              <button className="secondary" onClick={() => void remove()}>
                Cancel conversion
              </button>
            )}
            {!busy && job?.id && (
              <button className="secondary" onClick={() => void remove()}>
                Delete temporary files
              </button>
            )}
            {!busy && !service && !connecting && (
              <button className="secondary" onClick={() => void connect()}>
                Retry connection
              </button>
            )}
          </div>
          <p className="word-layout-hint">
            Fonts, table breaks and picture wrapping may change. Check the
            preview before sharing. Page numbers and contents may be
            recalculated.
          </p>
          <details className="input-support">
            <summary>Supported documents</summary>
            <p>
              Ordinary Chinese and English DOCX documents, tables, embedded
              pictures, headers, footnotes and contents. Complex layouts may
              change. Accept or reject tracked changes, remove comments, and
              show or remove hidden text in Word first. Password-protected
              files, macros, embedded files, embedded fonts and externally
              linked content are not supported in this first version.
            </p>
          </details>
        </section>
        <SeoContent tool="word" />
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
          description="Leaving will request deletion of temporary server files. Download your PDF first if you want to keep it."
          keep={() => setDestination("")}
          leave={leave}
        />
      )}
    </div>
  );
}
