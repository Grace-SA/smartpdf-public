import { useLayoutEffect, useRef, type ReactNode } from "react";

export function PreviewDialog({
  title,
  label,
  close,
  children,
  toolbar,
  previous,
  next,
}: {
  title: string;
  label: string;
  close: () => void;
  children: ReactNode;
  toolbar?: ReactNode;
  previous?: () => void;
  next?: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const touch = useRef<{ x: number; y: number } | null>(null);
  useLayoutEffect(() => {
    const previousFocus = document.activeElement;
    const node = ref.current!;
    node.showModal();
    return () => {
      node.close();
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected)
        previousFocus.focus({ preventScroll: true });
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="preview-dialog"
      aria-label={label}
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          const r = e.currentTarget.getBoundingClientRect();
          if (
            e.clientX < r.left ||
            e.clientX > r.right ||
            e.clientY < r.top ||
            e.clientY > r.bottom
          )
            close();
        }
      }}
      onKeyDown={(e) => {
        if ((e.target as HTMLElement).closest("input,select")) return;
        if (e.key === "ArrowLeft" && previous) {
          e.preventDefault();
          previous();
        }
        if (e.key === "ArrowRight" && next) {
          e.preventDefault();
          next();
        }
      }}
    >
      <div className="lightbox-header">
        <span>{title}</span>
        <button
          className="lightbox-close"
          aria-label="Close preview"
          title="Close (Esc)"
          onClick={close}
        >
          ×
        </button>
      </div>
      {(toolbar || previous || next) && (
        <div className="lightbox-toolbar">
          {(previous || next) && (
            <button
              className="lightbox-arrow previous"
              aria-label="Previous page"
              disabled={!previous}
              onClick={previous}
            >
              ‹
            </button>
          )}
          {toolbar}
          {(previous || next) && (
            <button
              className="lightbox-arrow next"
              aria-label="Next page"
              disabled={!next}
              onClick={next}
            >
              ›
            </button>
          )}
        </div>
      )}
      <div
        className="lightbox-stage"
        onTouchStart={(e) => {
          const t = e.touches[0];
          touch.current =
            e.touches.length === 1 && t ? { x: t.clientX, y: t.clientY } : null;
        }}
        onTouchEnd={(e) => {
          const start = touch.current;
          touch.current = null;
          const t = e.changedTouches[0];
          if (!start || !t) return;
          const target = e.target as HTMLElement;
          const scroller = target.closest(".page-detail-canvas");
          if (scroller && scroller.scrollWidth > scroller.clientWidth + 2)
            return;
          const dx = t.clientX - start.x,
            dy = t.clientY - start.y;
          if (Math.abs(dx) > 70 && Math.abs(dx) > Math.abs(dy) * 2) {
            if (dx < 0) next?.();
            else previous?.();
          }
        }}
      >
        {children}
      </div>
    </dialog>
  );
}
