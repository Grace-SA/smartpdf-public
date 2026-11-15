import { useEffect, useRef, useState } from "react";
import { FilePicker } from "../FilePicker";
import { ToolNavigation } from "../ToolNavigation";
import { toolPaths } from "../routes";
import { LeaveTaskDialog } from "../LeaveTaskDialog";
import { SeoContent, applySeo } from "../SeoContent";
import { checkPdfLocally } from "./preflight";
import { wordRequest as request } from "../word/errors";
import "../word/word.css";
import "./pdfword.css";

type Job = {
  id: string;
  state: string;
  pages?: number;
  warnings: string[];
  progress?: { completedPages: number; totalPages: number };
  error?: string;
  cleanupPending?: boolean;
};
type Service = {
  available: boolean;
  region: string;
  retentionMinutes: number;
  mode?: string;
  capabilities?: {
    reconstruction?: boolean;
    ocr?: boolean;
    stirlingNative?: boolean;
  };
};
const mime = "application/pdf";
const outputMime =
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
const stages: Record<string, string> = {
  created: "Ready to upload",
  uploading: "Uploading PDF…",
  queued: "Waiting for conversion…",
  checking: "Checking PDF…",
  starting: "Preparing conversion…",
  converting: "Creating editable Word text…",
  "checking-result": "Checking the Word document…",
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

export function PdfWordPage() {
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
  const [destination, setDestination] = useState("");
  const current = useRef<string | undefined>(undefined);
  const creating = useRef<Promise<Job> | null>(null);
  const controller = useRef<AbortController | null>(null);
  const checker = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  const alert = useRef<HTMLParagraphElement>(null);
  const complete = useRef<HTMLHeadingElement>(null);

  async function connect() {
    try {
      const next = await request<Service>("/api/pdfword/session");
      if (mounted.current) {
        setService(next);
        setError("");
      }
    } catch {
      if (mounted.current)
        setError(
          "Conversion is unavailable. Retry connection; your PDF has not been uploaded.",
        );
    }
  }
  useEffect(() => {
    applySeo("pdfword");
    mounted.current = true;
    const discard = () => {
      checker.current?.abort();
      controller.current?.abort();
      if (current.current)
        void fetch(`/api/pdfword/jobs/${current.current}`, {
          method: "DELETE",
          keepalive: true,
        }).catch(() => {});
    };
    const restore = (event: PageTransitionEvent) => {
      if (event.persisted) location.reload();
    };
    void request<Service>("/api/pdfword/session")
      .then((value) => {
        if (mounted.current) setService(value);
      })
      .catch(() => {
        if (mounted.current)
          setError(
            "Conversion is unavailable. Retry connection; your PDF has not been uploaded.",
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
      !/\.pdf$/i.test(next.name) ||
      !next.size ||
      next.size > 30 * 1024 ** 2
    ) {
      setError("Choose one PDF up to 30 MiB.");
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
      await checkPdfLocally(snapshot, abort.signal);
      if (!abort.signal.aborted && mounted.current) setChecked(true);
    } catch (cause) {
      if (!abort.signal.aborted && mounted.current)
        setError(
          cause instanceof Error ? cause.message : "Choose a valid PDF.",
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
    setResult(undefined);
    setUrl("");
    try {
      // Keep the creation response so cancellation can delete an already-created
      // empty job instead of losing its ID when the request is aborted.
      if (creating.current) {
        const created = await creating.current;
        current.current = created.id;
        creating.current = null;
      }
      if (current.current) {
        let deleted = await request<Job>(
          `/api/pdfword/jobs/${current.current}`,
          {
            method: "DELETE",
          },
        );
        const until = Date.now() + 30000;
        while (deleted.cleanupPending && Date.now() < until) {
          await new Promise((resolve) => setTimeout(resolve, 500));
          deleted = await request<Job>(`/api/pdfword/jobs/${current.current}`);
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
      creating.current ||
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
      const pending = request<Job>("/api/pdfword/jobs", {
        method: "POST",
      });
      creating.current = pending;
      const created = await pending;
      id = created.id;
      current.current = id;
      creating.current = null;
      if (abort.signal.aborted || !mounted.current) {
        if (!mounted.current)
          void fetch(`/api/pdfword/jobs/${id}`, {
            method: "DELETE",
            keepalive: true,
          }).catch(() => {});
        return;
      }
      setJob({ ...created, state: "uploading" });
      await new Promise<void>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("PUT", `/api/pdfword/jobs/${id}/input`);
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
          else reject(Error("Upload failed. Retry or choose a smaller PDF."));
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
            "Conversion took too long. Retry or choose a simpler PDF.",
          );
        const next = await request<Job>(`/api/pdfword/jobs/${id}`, {
          signal: abort.signal,
        });
        if (abort.signal.aborted || !mounted.current) return;
        setJob(next);
        if (["failed", "cancelled", "expired"].includes(next.state))
          throw Error(
            next.error ||
              "This conversion is unavailable. Choose the PDF again.",
          );
        if (next.state === "succeeded") {
          const response = await fetch(`/api/pdfword/jobs/${id}/result`, {
            signal: abort.signal,
          });
          if (!response.ok)
            throw Error("The result is unavailable. Retry conversion.");
          const bytes = await response.blob();
          if (
            bytes.size > 30 * 1024 ** 2 ||
            bytes.size < 4 ||
            (await bytes.slice(0, 2).text()) !== "PK"
          )
            throw Error("The Word document failed its checks.");
          if (abort.signal.aborted || !mounted.current) return;
          const pdf = new File(
            [bytes],
            input.name.replace(/\.pdf$/i, ".docx"),
            { type: outputMime },
          );
          setResult(pdf);
          setUrl(URL.createObjectURL(pdf));
          break;
        }
        await pause(abort.signal);
      }
    } catch (cause) {
      if (!id) creating.current = null;
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

  function navigate(href: string) {
    if (file || current.current) setDestination(href);
    else location.assign(href);
  }
  return (
    <div
      className="product-app word-app pdfword-app"
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
          active="pdfword"
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
            <h1>PDF to Word</h1>
            <p>
              {service?.capabilities?.reconstruction
                ? "Convert PDF text, tables and supported scans into Word."
                : "Turn simple text PDFs into editable Word documents."}
            </p>
          </div>
        </div>
        <section
          className="word-card"
          aria-label="PDF to Word conversion"
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
                    <h2>Drop your PDF here</h2>
                    <p>or choose a file from your device</p>
                  </>
                )}
              </div>
              <FilePicker
                id="pdfword-file"
                accept={`.pdf,${mime}`}
                disabled={busy || !!job?.id || cleanup}
                onChange={(event) => {
                  const input = event.currentTarget;
                  const files = Array.from(input.files || []);
                  void choose(files).finally(() => {
                    if (input.files?.[0] === files[0]) input.value = "";
                  });
                }}
              >
                {file ? "Change PDF" : "Select PDF file"}
              </FilePicker>
              {!file && (
                <p className="limits">
                  One PDF · up to 30 MiB · up to 200 pages
                </p>
              )}
            </div>
          )}
          {file && !job?.id && (
            <p role="status">
              {checking
                ? "Checking PDF on this device… Nothing is being uploaded."
                : checked
                  ? "Basic file checks passed. Text and layout are checked during conversion."
                  : "Choose a corrected PDF to continue."}
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
                Your PDF is uploaded only when you choose Upload and convert.{" "}
                {service
                  ? `Temporary files expire within ${service.retentionMinutes} minutes; you can delete them sooner.`
                  : "Connect to see processing details."}
              </p>
              <p>
                {service?.capabilities?.reconstruction
                  ? `Editable paragraphs and tables, with pictures retained. ${service.capabilities.ocr ? "Scanned pages are recognized with OCR." : "OCR is unavailable on this server."} Word layout and fonts may change.`
                  : "Simple text PDFs only. Scans, tables, columns and graphics are not supported yet. Word layout and fonts may change."}
              </p>
            </div>
          )}
          {busy && (
            <p role="status" aria-live="polite">
              {cleanup
                ? "Deleting temporary files…"
                : progress !== undefined
                  ? `Uploading PDF… ${progress}%`
                  : job?.progress
                    ? `Processing page ${Math.min(job.progress.completedPages + 1, job.progress.totalPages)} of ${job.progress.totalPages}…`
                    : stages[job?.state || "created"] ||
                      "Preparing conversion…"}
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
                {job?.warnings?.length
                  ? "Your Word document is ready for review"
                  : "Your Word document is ready"}
              </h2>
              <p className="word-filename">{result.name}</p>
              <p>{job?.pages} source pages · editable text</p>
              <p className="limits">
                {service?.region} · temporary files expire within{" "}
                {service?.retentionMinutes} minutes
              </p>
              <div className="word-actions">
                <a className="word-download" href={url} download={result.name}>
                  Download Word
                </a>
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
            {!busy && (!!job?.id || cleanup) && (
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
            <summary>Supported PDFs</summary>
            <p>
              {service?.capabilities?.reconstruction
                ? "Text PDFs and supported scans can produce editable paragraphs and tables. Pictures and formulas may be retained as images. Complex layouts, handwriting and poor scans need review. Check names, numbers, table cells and reading order before sharing. Password-protected and interactive PDFs must be unlocked or flattened first."
                : "Simple text PDFs with one column. The result contains editable text, with page sizes retained; exact fonts and line wrapping may change. Scans, tables, columns, pictures, passwords, annotations and interactive content are not supported yet. Unsupported files are refused in full. Check the Word document before sharing."}
            </p>
          </details>
        </section>
        <SeoContent
          tool="pdfword"
          faq={
            service?.capabilities?.reconstruction
              ? [
                  [
                    "Is my PDF uploaded?",
                    "Only when you choose Upload and convert. The processing location is shown above. Temporary files expire within one hour and can be deleted sooner.",
                  ],
                  [
                    "Which PDFs are supported?",
                    "Text, tables, pictures and supported scanned pages, up to 30 MiB and 200 pages. OCR availability depends on this server. Complex or unclear pages can require review or exceed processing limits.",
                  ],
                  [
                    "Will the Word layout match exactly?",
                    "The result is designed for editing. Pictures and some formulas remain images. Fonts, line wrapping and pagination can change. Check OCR text, numbers, table cells and reading order before sharing.",
                  ],
                ]
              : undefined
          }
        />
        <footer className="site-footer">
          <a href="/privacy/">Privacy and file handling</a>
          <a href="/notices/index.html">Third-party notices</a>
          {service?.capabilities?.stirlingNative && (
            <span>
              PDF conversion:{" "}
              <a href="https://github.com/Stirling-Tools/Stirling-Office-Convert">
                Stirling Office Convert
              </a>
            </span>
          )}
          {service?.capabilities?.reconstruction && (
            <span>
              OCR technology:{" "}
              <a href="https://github.com/SoMarkAI/OXR">
                Powered by SoMark OXR
              </a>
              {" · "}
              <a href="https://huggingface.co/baidu/Unlimited-OCR-2">
                Unlimited-OCR-2
              </a>
              {" · "}
              <a href="https://github.com/PaddlePaddle/PaddleOCR">PaddleOCR</a>
            </span>
          )}
        </footer>
      </main>
      {destination && (
        <LeaveTaskDialog
          description="Leaving requests deletion of temporary conversion files. Download your Word document first if you want to keep it."
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
