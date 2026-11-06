import { useEffect, useRef, useState } from "react";
import { FilePicker } from "../FilePicker";
import { FilePreview } from "../FilePreview";
import type { Engine } from "../platform/engine";
import { SeoContent, applySeo } from "../SeoContent";
import { ToolNavigation } from "../ToolNavigation";
import { toolPaths } from "../routes";
import { LeaveTaskDialog } from "../LeaveTaskDialog";
import "../word/word.css";
import { ExcelSettings } from "./ExcelSettings";
import { defaultOptions, type ExcelOptions, type Sheet } from "./workbook";

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
export function ExcelPage() {
  const [sheets, setSheets] = useState<Sheet[]>([]);
  const [options, setOptions] = useState<ExcelOptions>(defaultOptions);
  const [inspecting, setInspecting] = useState(false);
  const [adjusting, setAdjusting] = useState(false);
  const [dirty, setDirty] = useState(false);
  const inspection = useRef<AbortController | null>(null);
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
  const [destination, setDestination] = useState("");
  const leaving = useRef(false);
  const controller = useRef<AbortController | null>(null);
  const currentJob = useRef<string | undefined>(undefined);
  const mounted = useRef(true);
  async function connect() {
    setConnecting(true);
    try {
      const value = await request<Service>("/api/excel/session");
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
    applySeo("excel");
    mounted.current = true;
    const discard = () => {
      inspection.current?.abort();
      controller.current?.abort();
      if (currentJob.current)
        void fetch(`/api/excel/jobs/${currentJob.current}`, {
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
    void request<Service>("/api/excel/session")
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
      void fetch(`/api/excel/jobs/${currentJob.current}`, {
        method: "DELETE",
        keepalive: true,
      });
    location.assign(destination);
  }
  async function choose(files: File[]) {
    inspection.current?.abort();
    const check = new AbortController();
    inspection.current = check;
    setError("");
    setFile(undefined);
    setSheets([]);
    setOptions(defaultOptions());
    setResult(undefined);
    setPreview(undefined);
    setUrl("");
    setJob(undefined);
    setAdjusting(false);
    setDirty(false);
    setInspecting(false);
    if (files.length !== 1 || !/\.xlsx$/i.test(files[0]?.name || "")) {
      setError(
        "Choose one XLSX workbook. Save older .xls files as .xlsx in Excel first.",
      );
      return;
    }
    const selected = files[0]!;
    if (!selected.size || selected.size > 30 * 1024 ** 2) {
      setError("Choose a non-empty XLSX up to 30 MiB.");
      return;
    }
    setInspecting(true);
    try {
      const { inspectWorkbook } = await import("./metadata");
      const list = await inspectWorkbook(selected, check.signal);
      if (check.signal.aborted || !mounted.current) return;
      const visible = list
        .filter((sheet) => !sheet.hidden)
        .map((sheet) => sheet.index);
      if (!visible.length)
        throw new Error("This workbook has no visible worksheets to export.");
      setSheets(list);
      const active = list.find((sheet) => sheet.active && !sheet.hidden);
      setOptions({
        ...defaultOptions(),
        sheets: [active?.index ?? visible[0]!],
      });
      setFile(selected);
    } catch (cause) {
      if (!check.signal.aborted && mounted.current)
        setError(
          cause instanceof Error
            ? cause.message
            : "Workbook inspection failed.",
        );
    } finally {
      if (!check.signal.aborted && mounted.current) setInspecting(false);
    }
  }
  async function start() {
    if (!file || busy || inspecting || !options.sheets.length) return;
    const abort = new AbortController();
    controller.current = abort;
    setBusy(true);
    setError("");
    setProgress(undefined);
    setPreview(undefined);
    setResult(undefined);
    setUrl("");
    setAdjusting(false);
    let id: string | undefined;
    try {
      if (currentJob.current) {
        await request<Job>(`/api/excel/jobs/${currentJob.current}`, {
          method: "DELETE",
          signal: abort.signal,
        });
        currentJob.current = undefined;
      }
      const created = await request<Job>("/api/excel/jobs", {
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
        xhr.open("PUT", `/api/excel/jobs/${id}/input`);
        xhr.setRequestHeader(
          "Content-Type",
          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        );
        xhr.setRequestHeader("X-Excel-Options", JSON.stringify(options));
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
                  "Upload could not finish. Retry with a XLSX up to 30 MiB.",
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
            "Conversion took too long. Retry or export from Excel.",
          );
        const next = await request<Job>(`/api/excel/jobs/${id}`, {
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
          const response = await fetch(`/api/excel/jobs/${id}/result`, {
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
          const pdf = new File([blob], file.name.replace(/\.xlsx$/i, ".pdf"), {
            type: "application/pdf",
          });
          setResult(pdf);
          setUrl(URL.createObjectURL(pdf));
          setDirty(false);
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
        void fetch(`/api/excel/jobs/${id}`, {
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
        let next = await request<Job>(`/api/excel/jobs/${id}`, {
          method: "DELETE",
        });
        setJob(next);
        const deadline = Date.now() + 30000;
        while (next.cleanupPending && Date.now() < deadline) {
          await new Promise((resolve) => setTimeout(resolve, 500));
          next = await request<Job>(`/api/excel/jobs/${id}`);
          setJob(next);
        }
        if (next.cleanupPending)
          throw new Error(
            "Access has been removed. Server cleanup is still in progress; retry deletion shortly.",
          );
      }
      currentJob.current = undefined;
      setFile(undefined);
      setSheets([]);
      setOptions(defaultOptions());
      setDirty(false);
      setAdjusting(false);
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
      className="product-app word-app excel-app"
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
          active="excel"
          keepCurrent
          disabled={busy}
          choose={(tool) => navigate(toolPaths[tool])}
        />
        <span className="version">Excel to PDF</span>
      </header>
      <main className="word-page">
        <div className="task-heading">
          <a className="secondary" href="/">
            ← All tools
          </a>
          <div>
            <h1>Excel to PDF</h1>
            <p>Convert your spreadsheet to PDF.</p>
          </div>
        </div>
        <section
          className={`word-card${dragging ? " is-dragging" : ""}`}
          aria-label="Excel to PDF conversion"
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
            if (!busy && !result)
              void choose(Array.from(event.dataTransfer.files));
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
                  d="M30 2v15h15M15 27h22v16H15zM15 32h22M15 38h22M22 27v16M29 27v16M15 48h22"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <div className="word-selection-copy">
                {file ? (
                  <>
                    <p className="excel-filename">
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
                        : "Drop your Excel workbook here"}
                    </h2>
                    <p>or choose a file from your device</p>
                  </>
                )}
              </div>
              <FilePicker
                id="excel-file"
                accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                disabled={busy}
                onChange={(event) => {
                  const files = Array.from(event.target.files || []);
                  event.target.value = "";
                  if (files.length) void choose(files);
                }}
              >
                {file ? "Change document" : "Choose an Excel workbook"}
              </FilePicker>
              {!file && (
                <p className="limits">
                  One XLSX · up to 30 MiB · up to 500 output pages
                </p>
              )}
            </div>
          )}
          {inspecting && (
            <p role="status">Reading worksheet names on this device…</p>
          )}
          {file && !result && (
            <ExcelSettings
              sheets={sheets}
              value={options}
              disabled={busy}
              change={(next) => {
                setOptions(next);
                setDirty(true);
                setPreview(undefined);
              }}
            />
          )}
          <p className="word-layout-hint">
            Processing:{" "}
            {service?.region || (connecting ? "connecting…" : "unavailable")}.
            Temporary files auto-delete within one hour.
          </p>
          {busy && (
            <div role="status" aria-live="polite">
              <p>
                {job?.state === "cancelled"
                  ? "Removing temporary files…"
                  : stages[job?.state || "created"] || "Connecting…"}
              </p>
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
              <details className="input-support">
                <summary>Conversion details</summary>
                <ul>
                  {job?.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
                <p>
                  Selected worksheets:{" "}
                  {sheets
                    .filter((sheet) => options.sheets.includes(sheet.index))
                    .map((sheet) => sheet.name)
                    .join(", ")}
                </p>
              </details>
              {dirty && (
                <p role="status">
                  Settings have changed. Update the PDF before downloading.
                </p>
              )}
              <div className="word-actions">
                <button
                  className="secondary"
                  onClick={() => void showPreview()}
                  disabled={opening || dirty}
                >
                  {opening ? "Opening preview…" : "Preview PDF"}
                </button>
                {!dirty && (
                  <a
                    className="word-download"
                    href={url}
                    download={result.name}
                  >
                    Download PDF
                  </a>
                )}
                {!adjusting && (
                  <button
                    className="secondary"
                    onClick={() => setAdjusting(true)}
                  >
                    Adjust pagination
                  </button>
                )}
                {adjusting && (
                  <button
                    className="word-convert"
                    disabled={
                      busy ||
                      !dirty ||
                      !options.sheets.length ||
                      !service?.available
                    }
                    onClick={() => void start()}
                  >
                    Update PDF
                  </button>
                )}
              </div>
              {adjusting && (
                <ExcelSettings
                  sheets={sheets}
                  value={options}
                  disabled={busy}
                  change={(next) => {
                    setOptions(next);
                    setDirty(true);
                    setPreview(undefined);
                  }}
                />
              )}
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
                  inspecting ||
                  !options.sheets.length
                }
              >
                Convert to PDF
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
          <details className="input-support">
            <summary>Supported documents</summary>
            <p>
              Ordinary XLSX workbooks with up to 50 worksheets and 200,000
              cells. Only selected visible sheets are exported. Existing print
              areas are kept. Formula values last saved in Excel are used
              without recalculation. Recalculate and save in Excel first if
              needed. Common charts, embedded PNG/JPEG and static SVG pictures,
              common conditional formatting and filtered tables are supported.
              Check their layout, colours and visible rows in the PDF preview.
              Ordinary named ranges, cell notes and read-only sheet protection
              are supported. Macros, external data, encrypted files and newer
              chart types may require exporting from Excel instead. Creates
              searchable PDFs. Screen-reader table tags are not preserved.
            </p>
          </details>
        </section>
        <SeoContent tool="excel" />
        <footer className="site-footer">
          <a href="/privacy/">Privacy and file handling</a>
          <a href="/notices/index.html">Third-party notices</a>
        </footer>
      </main>
      {preview && result && !dirty && (
        <FilePreview
          file={result}
          engine={preview}
          profile="excel"
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
