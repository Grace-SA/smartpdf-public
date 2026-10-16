import { useEffect, useRef, useState } from "react";
import { ConfirmDialog } from "./ConfirmDialog";

/** One handle for pointer dragging and a precise keyboard/touch alternative. */
export function CardMove({
  index,
  count,
  label,
  disabled,
  move,
}: {
  index: number;
  count: number;
  label: string;
  disabled: boolean;
  move: (to: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState("1");
  const cleanup = useRef<(() => void) | null>(null);
  const dragged = useRef(false);
  const suppressClickUntil = useRef(0);
  useEffect(() => {
    if (disabled) cleanup.current?.();
  }, [disabled]);
  useEffect(() => () => cleanup.current?.(), []);
  const value = Number(position);
  return (
    <>
      <button
        className="secondary card-move"
        disabled={disabled}
        aria-label={`Move ${label}`}
        title="Drag to reorder, or tap to choose a position"
        onClick={() => {
          if (performance.now() < suppressClickUntil.current) return;
          setPosition(String(index + 1));
          setOpen(true);
        }}
        onPointerDown={(event) => {
          if (disabled || event.button !== 0 || !event.isPrimary) return;
          const handle = event.currentTarget;
          const root = handle.closest<HTMLElement>("[data-reorder-list]");
          if (!root) return;
          event.stopPropagation();
          handle.setPointerCapture(event.pointerId);
          let target = index,
            x = event.clientX,
            y = event.clientY;
          const startX = x,
            startY = y;
          let frame = 0;
          dragged.current = false;
          const clearMark = () =>
            root
              .querySelectorAll("[data-drop-target]")
              .forEach((e) => e.removeAttribute("data-drop-target"));
          const locate = () => {
            const card = document
              .elementFromPoint(x, y)
              ?.closest<HTMLElement>("[data-sort-index]");
            clearMark();
            target = -1;
            if (card && root.contains(card)) {
              target = Number(card.dataset.sortIndex);
              card.setAttribute("data-drop-target", "true");
            }
          };
          const tick = () => {
            if (dragged.current) {
              const rect = root.getBoundingClientRect();
              if (y < rect.top + 42) root.scrollTop -= 10;
              else if (y > rect.bottom - 42) root.scrollTop += 10;
              locate();
            }
            frame = requestAnimationFrame(tick);
          };
          const onMove = (e: PointerEvent) => {
            if (e.pointerId !== event.pointerId) return;
            x = e.clientX;
            y = e.clientY;
            if (Math.hypot(x - startX, y - startY) > 6) dragged.current = true;
            if (dragged.current) {
              e.preventDefault();
              locate();
            }
          };
          const clean = () => {
            cancelAnimationFrame(frame);
            clearMark();
            handle.removeEventListener("pointermove", onMove);
            handle.removeEventListener("pointerup", finish);
            handle.removeEventListener("pointercancel", cancel);
            if (handle.hasPointerCapture(event.pointerId))
              handle.releasePointerCapture(event.pointerId);
            cleanup.current = null;
          };
          const finish = () => {
            const commit = dragged.current;
            if (commit) suppressClickUntil.current = performance.now() + 250;
            clean();
            if (commit && target >= 0 && target !== index) move(target);
          };
          const cancel = () => {
            clean();
            dragged.current = true;
          };
          cleanup.current = clean;
          handle.addEventListener("pointermove", onMove);
          handle.addEventListener("pointerup", finish);
          handle.addEventListener("pointercancel", cancel);
          frame = requestAnimationFrame(tick);
        }}
      >
        ⠿
      </button>
      {open && (
        <ConfirmDialog
          cancelLabel="Cancel"
          title={`Move ${label}`}
          onCancel={() => setOpen(false)}
          action={
            <button
              disabled={
                disabled ||
                !Number.isInteger(value) ||
                value < 1 ||
                value > count ||
                value === index + 1
              }
              onClick={() => {
                move(value - 1);
                setOpen(false);
              }}
            >
              Move here
            </button>
          }
        >
          <label>
            New position{" "}
            <input
              type="number"
              inputMode="numeric"
              min={1}
              max={count}
              value={position}
              onChange={(e) => setPosition(e.target.value)}
            />
          </label>
          <p>Choose a position from 1 to {count}.</p>
        </ConfirmDialog>
      )}
    </>
  );
}
