import { useEffect, useRef } from "react";
import type { CompressionSummary } from "./compress/model";
export type DownloadNotice = { kind: "status" | "error"; text: string } | null;
export function Completion({
  title,
  files,
  pages,
  packing,
  disabled,
  notice,
  download,
  restart,
  compression,
  imageResult,
}: {
  imageResult?: import("./raster/model").RasterResult | null;
  title: string;
  files: File[];
  pages: number;
  packing: boolean;
  disabled: boolean;
  notice: DownloadNotice;
  download: () => void;
  restart: () => void;
  compression?: CompressionSummary | null;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const focused = useRef(false);
  useEffect(() => {
    if (disabled || focused.current) return;
    // Wait for the processing dialog to close and restore its previous focus.
    const frame = requestAnimationFrame(() => {
      heading.current?.focus({ preventScroll: true });
      focused.current = true;
    });
    return () => cancelAnimationFrame(frame);
  }, [disabled]);
  const bytes = files.reduce((sum, file) => sum + file.size, 0);
  const size =
    bytes < 1024 * 1024
      ? `${Math.max(1, Math.round(bytes / 1024))} KB`
      : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  const multiple = files.length > 1;
  return (
    <section className="delivery" aria-label="Completed task">
      <div className="completion-mark" aria-hidden="true">
        <svg
          width="28"
          height="28"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path d="m5 12 4 4L19 6" />
        </svg>
      </div>
      <h1 ref={heading} tabIndex={-1}>
        {title}
      </h1>
      <p className="completion-subtitle">
        {compression?.alreadyOptimized
          ? "No smaller safe result was found. Images may already be compressed or use transparency and filters this version keeps unchanged. The original bytes were kept."
          : "Created locally. Your originals are unchanged."}
      </p>
      <div className="output-summary">
        <svg
          width="24"
          height="28"
          viewBox="0 0 24 28"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          aria-hidden="true"
        >
          <path d="M5 2h9l6 6v18H5zM14 2v7h6M9 15h7m-7 5h7" />
        </svg>
        <div>
          <strong title={multiple ? undefined : files[0]?.name}>
            {multiple
              ? `${files.length} PDF files · ZIP download`
              : files[0]?.name}
          </strong>
          <span>
            {imageResult ? (
              <>
                {imageResult.count} {imageResult.format.toUpperCase()}{" "}
                {imageResult.count === 1 ? "image" : "images"} · {size}
              </>
            ) : compression ? (
              <>
                {pages} {pages === 1 ? "page" : "pages"} ·{" "}
                {formatBytes(compression.originalBytes)} →{" "}
                {formatBytes(compression.outputBytes)} ·{" "}
                {compression.alreadyOptimized
                  ? "Already optimized"
                  : `${compression.savedPercent}% saved`}
              </>
            ) : (
              <>
                {pages} {pages === 1 ? "page" : "pages"}
                {multiple ? " total" : ""} · {size}
                {multiple ? " before packaging" : ""}
              </>
            )}
          </span>
        </div>
      </div>
      <button
        className="download-primary"
        disabled={disabled || !files.length}
        onClick={download}
      >
        <svg
          aria-hidden="true"
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5" />
        </svg>
        {packing
          ? "Preparing download…"
          : imageResult
            ? imageResult.count > 1
              ? "Download ZIP"
              : `Download ${imageResult.format.toUpperCase()}`
            : multiple
              ? "Download all PDFs (ZIP)"
              : "Download PDF"}
      </button>
      <div className="download-feedback">
        <p role="status">{notice?.kind === "status" ? notice.text : ""}</p>
        {notice?.kind === "error" && (
          <p role="alert" className="download-error">
            {notice.text}
          </p>
        )}
      </div>
      <div className="completion-restart">
        <button className="result-back" disabled={disabled} onClick={restart}>
          <span aria-hidden="true">←</span> Choose new files
        </button>
        <p>Download first—this starts a new task.</p>
      </div>
      <p className="result-privacy">Processed locally · Nothing was uploaded</p>
    </section>
  );
}

function formatBytes(bytes: number) {
  return bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
