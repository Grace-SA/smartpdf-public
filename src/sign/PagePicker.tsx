import { useEffect, useRef, useState } from "react";
import type { RenderTask } from "pdfjs-dist/legacy/build/pdf.mjs";
import type { Preview } from "../platform/engine";
import { ConfirmDialog } from "../ConfirmDialog";
import { acquirePageRender } from "./ContinuousCanvas";
function Thumbnail({
  preview,
  page,
  choose,
  count,
  current = false,
}: {
  preview: Preview;
  page: number;
  choose: () => void;
  count: number;
  current?: boolean;
}) {
  const host = useRef<HTMLButtonElement>(null),
    canvas = useRef<HTMLCanvasElement>(null),
    [visible, setVisible] = useState(false);
  useEffect(() => {
    const obs = new IntersectionObserver(([entry]) => {
      setVisible(!!entry?.isIntersecting);
    });
    obs.observe(host.current!);
    return () => obs.disconnect();
  }, []);
  useEffect(() => {
    if (!visible) {
      canvas.current!.width = canvas.current!.height = 0;
      return;
    }
    let stopped = false,
      task: RenderTask | undefined;
    const c = document.createElement("canvas"),
      controller = new AbortController();
    void (async () => {
      let release: (() => void) | undefined;
      try {
        release = await acquirePageRender(controller.signal);
        if (stopped) return;
        const p = await preview.doc.getPage(page + 1);
        if (stopped) return;
        const base = p.getViewport({ scale: 1 }),
          v = p.getViewport({
            scale: Math.min(130 / base.width, 170 / base.height),
          });
        c.width = Math.ceil(v.width);
        c.height = Math.ceil(v.height);
        task = p.render({
          canvas: c,
          canvasContext: c.getContext("2d")!,
          viewport: v,
          annotationMode: 1,
        });
        await task.promise;
        if (!stopped && canvas.current) {
          canvas.current.width = c.width;
          canvas.current.height = c.height;
          canvas.current.getContext("2d")!.drawImage(c, 0, 0);
        }
      } catch {
        /* Page number remains usable when a thumbnail cannot render. */
      } finally {
        c.width = c.height = 0;
        release?.();
      }
    })();
    return () => {
      stopped = true;
      controller.abort();
      task?.cancel();
    };
  }, [visible, preview, page]);
  return (
    <button
      ref={host}
      className="secondary sign-page-thumb"
      aria-current={current ? "page" : undefined}
      onClick={choose}
    >
      <canvas ref={canvas} />
      <span>
        Page {page + 1}
        {count ? ` · ${count} signed` : ""}
      </span>
    </button>
  );
}
export function PageThumbnails({
  preview,
  counts,
  current,
  choose,
}: {
  preview: Preview;
  counts: number[];
  current: number;
  choose: (page: number) => void;
}) {
  const list = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const button = list.current?.querySelector<HTMLElement>(
      '[aria-current="page"]',
    );
    const rail = list.current?.parentElement;
    if (!button || !rail) return;
    const b = button.getBoundingClientRect(),
      r = rail.getBoundingClientRect();
    if (b.top < r.top + 50) rail.scrollTop -= r.top + 50 - b.top;
    else if (b.bottom > r.bottom) rail.scrollTop += b.bottom - r.bottom;
  }, [current]);
  return (
    <div ref={list} className="sign-thumbnail-list">
      {counts.map((count, index) => (
        <Thumbnail
          key={index}
          preview={preview}
          page={index}
          count={count}
          current={index === current}
          choose={() => choose(index)}
        />
      ))}
    </div>
  );
}
export function PagePicker({
  preview,
  choose,
  close,
  counts,
}: {
  preview: Preview;
  choose: (page: number) => void;
  close: () => void;
  counts: number[];
}) {
  return (
    <ConfirmDialog
      title="Choose a page"
      onCancel={close}
      cancelLabel="Close"
      action={null}
    >
      <div className="sign-page-grid">
        {counts.map((count, page) => (
          <Thumbnail
            key={page}
            preview={preview}
            page={page}
            count={count}
            choose={() => choose(page)}
          />
        ))}
      </div>
    </ConfirmDialog>
  );
}
