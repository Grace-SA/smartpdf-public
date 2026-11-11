import { useEffect, useEffectEvent, useRef, useState } from "react";
import { FilePicker } from "../FilePicker";
import { ToolNavigation } from "../ToolNavigation";
import { applySeo, SeoContent } from "../SeoContent";
import { validatePdf, validPages, outputName } from "./model";
import "./pdf-excel.css";
import { toolPaths } from "../routes";
import { LeaveTaskDialog } from "../LeaveTaskDialog";
type Service = {
  available: boolean;
  ocr: boolean;
  region: string;
  retentionMinutes: number;
};
type Preview = {
  sheet: string;
  page: number;
  rows: number;
  columns: number;
  values: string[][];
};
type Job = {
  id: string;
  state: string;
  error?: string;
  tables?: number;
  sheets?: number;
  warnings?: string[];
  preview?: Preview[];
};
const base = "/api/pdf-to-excel";
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(base + path, { credentials: "same-origin", ...init });
  const value = await r.json();
  if (!r.ok)
    throw Error(
      value.error || "The conversion service is unavailable. Try again.",
    );
  return value;
}
const pause = (signal: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const done = () => {
      signal.removeEventListener("abort", abort);
      resolve();
    };
    const timer = setTimeout(done, 500);
    const abort = () => {
      clearTimeout(timer);
      reject(new DOMException("Cancelled", "AbortError"));
    };
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
  });
export function PdfExcelPage() {
  const [service, setService] = useState<Service>();
  const [destination, setDestination] = useState("");
  const leaving = useRef(false);
  const [connecting, setConnecting] = useState(true);
  const [file, setFile] = useState<File>();
  const [pages, setPages] = useState("");
  const [layout, setLayout] = useState("tables");
  const [ocr, setOcr] = useState(false);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState("");
  const [error, setError] = useState("");
  const [job, setJob] = useState<Job>();
  const [url, setUrl] = useState("");
  const [sheet, setSheet] = useState(0);
  const control = useRef<AbortController | null>(null);
  const id = useRef("");
  const generation = useRef(0);
  const locked = useRef(false);
  const mounted = useRef(true);
  async function connect() {
    try {
      const value = await request<Service>("/session");
      if (mounted.current) {
        setService(value);
        setOcr(value.ocr);
        setError(
          value.available
            ? ""
            : "Conversion is temporarily unavailable. Retry connecting.",
        );
      }
    } catch {
      if (mounted.current)
        setError("Could not connect. Your PDF has not been uploaded.");
    } finally {
      if (mounted.current) setConnecting(false);
    }
  }
  const discard = () => {
    generation.current++;
    control.current?.abort();
    const old = id.current;
    id.current = "";
    if (old)
      void fetch(base + "/jobs/" + old, { method: "DELETE", keepalive: true });
    locked.current = false;
  };
  const restore = useEffectEvent((event: PageTransitionEvent) => {
    if (event.persisted) {
      reset();
      void connect();
    }
  });
  useEffect(() => {
    mounted.current = true;
    applySeo("pdfExcel");
    void request<Service>("/session")
      .then((value) => {
        if (!mounted.current) return;
        setService(value);
        setOcr(value.ocr);
        if (!value.available)
          setError("Conversion is temporarily unavailable. Retry connecting.");
      })
      .catch(() => {
        if (mounted.current)
          setError("Could not connect. Your PDF has not been uploaded.");
      })
      .finally(() => {
        if (mounted.current) setConnecting(false);
      });
    window.addEventListener("pageshow", restore);
    const hide = () => discard();
    window.addEventListener("pagehide", hide);
    return () => {
      mounted.current = false;
      window.removeEventListener("pagehide", hide);
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
      if (!leaving.current && (busy || file || url)) event.preventDefault();
    };
    window.addEventListener("beforeunload", before);
    return () => window.removeEventListener("beforeunload", before);
  }, [busy, file, url]);
  function choose(files: File[]) {
    if (locked.current) return;
    discard();
    setJob(undefined);
    setUrl("");
    setSheet(0);
    setPages("");
    const next = files[0];
    const problem =
      files.length !== 1
        ? "Choose one PDF at a time."
        : next
          ? validatePdf(next)
          : "Choose a PDF.";
    setError(problem);
    setFile(problem ? undefined : next);
  }
  async function start() {
    if (locked.current || !file || !service?.available) return;
    if (!validPages(pages)) {
      setError("Use page numbers such as 1-3,5, up to page 200.");
      return;
    }
    discard();
    locked.current = true;
    setBusy(true);
    setError("");
    setJob(undefined);
    setUrl("");
    setStage("Uploading your PDF…");
    const current = ++generation.current;
    const controller = new AbortController();
    control.current = controller;
    try {
      const params = new URLSearchParams({
        pages: pages.trim() || "all",
        layout,
        ocr: String(ocr),
      });
      const created = await request<Job>("/jobs?" + params, {
        method: "POST",
        headers: { "Content-Type": "application/pdf" },
        body: file,
        signal: controller.signal,
      });
      if (current !== generation.current) {
        void fetch(base + "/jobs/" + created.id, { method: "DELETE" });
        return;
      }
      id.current = created.id;
      let result = created;
      while (!["succeeded", "failed", "cancelled"].includes(result.state)) {
        setStage(
          result.state === "queued"
            ? "Waiting for conversion…"
            : "Extracting and checking tables…",
        );
        await pause(controller.signal);
        result = await request<Job>("/jobs/" + created.id, {
          signal: controller.signal,
        });
      }
      if (result.state !== "succeeded")
        throw Error(result.error || "Conversion was cancelled.");
      setStage("Preparing your Excel file…");
      const response = await fetch(base + "/jobs/" + created.id + "/download", {
        signal: controller.signal,
      });
      if (!response.ok)
        throw Error(
          "The workbook could not be downloaded. Try converting again.",
        );
      const blob = await response.blob();
      if (current !== generation.current) return;
      setUrl(URL.createObjectURL(blob));
      setJob(result);
      setSheet(0);
    } catch (e) {
      if (current === generation.current && !controller.signal.aborted)
        setError(
          e instanceof Error ? e.message : "Conversion failed. Try again.",
        );
    } finally {
      if (current === generation.current) {
        locked.current = false;
        setBusy(false);
      }
    }
  }
  function cancel() {
    discard();
    setBusy(false);
    setStage("");
    setError("Conversion cancelled. You can change settings and try again.");
  }
  function reset() {
    discard();
    setBusy(false);
    setFile(undefined);
    setJob(undefined);
    setUrl("");
    setError("");
    setPages("");
  }
  function navigate(target: string) {
    if (file || busy || url) setDestination(target);
    else location.assign(target);
  }
  const preview = job?.preview?.[sheet];
  return (
    <div
      className="product-app pdf-excel-page"
      onClick={(event) => {
        const target =
          event.target instanceof Element
            ? event.target.closest("a[href]")
            : null;
        if (
          target instanceof HTMLAnchorElement &&
          !event.defaultPrevented &&
          !target.hasAttribute("download") &&
          !event.metaKey &&
          !event.ctrlKey &&
          !event.shiftKey &&
          !event.altKey &&
          event.button === 0 &&
          target.origin === location.origin &&
          (file || busy || url)
        ) {
          event.preventDefault();
          navigate(target.href);
        }
      }}
    >
      <header className="px-header">
        <a className="brand" href="/" aria-label="Smart PDF home">
          <span className="brand-mark">S</span>
          <span className="brand-wordmark">
            Smart<strong>PDF</strong>
          </span>
        </a>
        <ToolNavigation
          active="pdfExcel"
          keepCurrent={true}
          disabled={busy}
          choose={(tool) => navigate(toolPaths[tool])}
        />
      </header>
      <main className="px-main">
        <a className="secondary px-back" href="/">
          ← All tools
        </a>
        <p className="px-eyebrow">CONVERT PDF</p>
        <h1>{url ? "Your Excel file is ready" : "PDF to Excel"}</h1>
        <p className="px-lead">
          {url
            ? "Check the table preview, then download your editable workbook."
            : "Turn PDF tables into editable Excel worksheets."}
        </p>
        {error && (
          <div className="px-alert" role="alert">
            {error}
          </div>
        )}
        {url && job ? (
          <>
            <section className="px-result">
              <p>
                {job.tables} tables · {job.sheets} worksheets
              </p>
              <a
                className="px-primary"
                href={url}
                download={outputName(file?.name || "converted.pdf")}
              >
                Download Excel
              </a>
              <button className="px-secondary" onClick={reset}>
                Convert another PDF
              </button>
            </section>
            <section className="px-review" aria-label="Conversion notes">
              <h2>Check before using your data</h2>
              <ul>
                {job.warnings?.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </section>
            {preview && (
              <section className="px-preview">
                <label htmlFor="px-sheet">Table preview</label>
                <select
                  id="px-sheet"
                  value={sheet}
                  onChange={(e) => setSheet(Number(e.target.value))}
                >
                  {job.preview?.map((p, i) => (
                    <option key={i} value={i}>
                      Page {p.page} · {p.sheet}
                    </option>
                  ))}
                </select>
                <p>
                  {preview.rows} rows × {preview.columns} columns. Preview shows
                  up to 12 rows and columns; long cell text is shortened.
                </p>
                <div className="px-table-scroll" tabIndex={0}>
                  <table>
                    <tbody>
                      {preview.values.map((r, i) => (
                        <tr key={i}>
                          {r.map((c, j) => (
                            <td key={j}>{c}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}
          </>
        ) : (
          <section
            className="px-card"
            onDragOver={(e) => {
              if (!busy) e.preventDefault();
            }}
            onDrop={(e) => {
              e.preventDefault();
              if (!busy) choose(Array.from(e.dataTransfer.files));
            }}
          >
            {!file ? (
              <div className="px-drop">
                <div className="px-doc" aria-hidden="true">
                  PDF → XLSX
                </div>
                <h2>Select a PDF</h2>
                <p>Tables, statements and reports</p>
                <FilePicker
                  id="pdf-excel-input"
                  accept=".pdf,application/pdf"
                  disabled={busy}
                  onChange={(e) => {
                    choose(Array.from(e.target.files || []));
                    e.target.value = "";
                  }}
                >
                  Choose PDF file
                </FilePicker>
                <p className="px-muted">
                  or drop it here · 30 MiB · up to 200 pages
                </p>
              </div>
            ) : (
              <>
                <div className="px-file">
                  <span>
                    <strong>{file.name}</strong>
                    <small>
                      {(file.size / 1024 / 1024).toFixed(2)} MiB · Original
                      stays unchanged
                    </small>
                  </span>
                  <button disabled={busy} onClick={reset}>
                    Change file
                  </button>
                </div>
                <fieldset disabled={busy} className="px-options">
                  <legend>Workbook settings</legend>
                  <label htmlFor="px-pages">Pages</label>
                  <input
                    id="px-pages"
                    value={pages}
                    placeholder="All pages"
                    onChange={(e) => setPages(e.target.value)}
                    aria-describedby="px-pages-help"
                  />
                  <small id="px-pages-help">
                    Leave blank for all pages, or enter 1-3,5.
                  </small>
                  <label htmlFor="px-layout">Worksheet layout</label>
                  <select
                    id="px-layout"
                    value={layout}
                    onChange={(e) => setLayout(e.target.value)}
                  >
                    <option value="tables">One worksheet per table</option>
                    <option value="single">All tables in one worksheet</option>
                  </select>
                  <small>
                    One worksheet stacks tables in source order; it does not
                    combine their columns.
                  </small>
                  <label className="px-check">
                    <input
                      type="checkbox"
                      checked={ocr}
                      disabled={!service?.ocr}
                      onChange={(e) => setOcr(e.target.checked)}
                    />{" "}
                    Recognize scanned pages (OCR)
                  </label>
                  {!service?.ocr && (
                    <small>
                      OCR is unavailable on this server. Text-based PDFs are
                      supported.
                    </small>
                  )}
                </fieldset>
                <p className="px-muted">
                  Text, leading zeros and long numbers are preserved as text.
                  Images and non-table paragraphs are excluded. Check OCR
                  results against your PDF.
                </p>
                {busy ? (
                  <div className="px-progress">
                    <p role="status">{stage}</p>
                    <progress aria-label="Conversion in progress" />
                    <button onClick={cancel}>Cancel conversion</button>
                  </div>
                ) : (
                  <button
                    className="px-primary"
                    disabled={
                      !service?.available || connecting || !validPages(pages)
                    }
                    onClick={() => void start()}
                  >
                    Upload and convert
                  </button>
                )}
              </>
            )}
          </section>
        )}
        {!url && (
          <aside className="px-privacy">
            <strong>Self-hosted server processing</strong>
            <p>
              Your PDF uploads only when you choose Upload and convert.{" "}
              {service
                ? `${service.region}. Temporary files expire within ${service.retentionMinutes} minutes; cancelling or starting another task deletes them sooner.`
                : "Connecting to the conversion service…"}
            </p>
            {!connecting && (!service || !service.available) && (
              <button
                onClick={() => {
                  setConnecting(true);
                  void connect();
                }}
              >
                Retry connection
              </button>
            )}
          </aside>
        )}
        {!url && <SeoContent tool="pdfExcel" />}
      </main>
      {destination && (
        <LeaveTaskDialog
          description="Your current conversion and temporary server files will be discarded."
          keep={() => setDestination("")}
          leave={() => {
            leaving.current = true;
            discard();
            location.assign(destination);
          }}
        />
      )}
      <footer className="px-footer">
        Smart PDF · Your original stays unchanged.
      </footer>
    </div>
  );
}
