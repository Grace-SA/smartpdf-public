import { useEffect, useMemo, useRef, useState } from "react";
import type { Engine, Preview } from "./platform/engine";
import { PreviewDialog } from "./PreviewDialog";
import { PageDetail } from "./organize/PageDetail";
import { LIMITS } from "./core/contracts";

/** A read-only preview: it never selects or commits a session document. */
export function FilePreview({
  file,
  engine,
  existing,
  close,
}: {
  file: File;
  engine: Engine;
  existing?: Preview;
  close: () => void;
}) {
  const [preview, setPreview] = useState<Preview | undefined>(existing);
  const [status, setStatus] = useState("Opening preview…");
  const focus = useRef(document.activeElement);
  useEffect(() => {
    if (existing) return;
    const controller = new AbortController();
    let owned: Preview | undefined;
    const timer = window.setTimeout(() => {
      controller.abort();
      setStatus(
        "Preview took too long. Close and try again. Your files are unchanged.",
      );
    }, LIMITS.timeoutMs);
    void engine
      .open(file, controller.signal, setStatus)
      .then(async (result) => {
        clearTimeout(timer);
        if (controller.signal.aborted) {
          await result.dispose();
          return;
        }
        owned = result;
        setPreview(result);
      })
      .catch(() => {
        clearTimeout(timer);
        if (!controller.signal.aborted)
          setStatus(
            "Could not open this preview. Your files are unchanged; you can still download the PDF.",
          );
      });
    return () => {
      clearTimeout(timer);
      controller.abort();
      void owned?.dispose();
    };
  }, [file, engine, existing]);
  useEffect(
    () => () => {
      const target = focus.current;
      if (target instanceof HTMLElement && target.isConnected) target.focus();
    },
    [],
  );
  const entries = useMemo(
    () =>
      preview
        ? Array.from({ length: preview.doc.numPages }, (_, source) => ({
            id: `preview-${source}`,
            source,
            turns: 0,
            position: source + 1,
          }))
        : [],
    [preview],
  );
  return preview ? (
    <PageDetail
      preview={preview}
      entries={entries}
      close={close}
      title={file.name}
    />
  ) : (
    <PreviewDialog title={file.name} label="PDF preview" close={close}>
      <p role="status">{status}</p>
    </PreviewDialog>
  );
}
