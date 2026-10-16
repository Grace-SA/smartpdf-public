import { useLayoutEffect, useRef } from "react";
import { createPortal } from "react-dom";

export function TaskNotice({
  working,
  message,
  close,
  adjust,
  title,
}: {
  working: boolean;
  message: string;
  close: () => void;
  adjust?: () => void;
  title?: string;
}) {
  const dialog = useRef<HTMLDivElement>(null);
  // A processing notice must never put the document in the browser's native
  // modal state: iOS may retain that state across completion/file selection.
  useLayoutEffect(() => {
    const previous = document.activeElement;
    const node = dialog.current!;
    const backdrop = node.parentElement!;
    const background = Array.from(document.body.children)
      .filter(
        (element): element is HTMLElement =>
          element instanceof HTMLElement && element !== backdrop,
      )
      .map((element) => ({ element, inert: element.inert }));
    for (const { element } of background) element.inert = true;
    const overflow = document.documentElement.style.overflow;
    document.documentElement.style.overflow = "hidden";
    Array.from(node.querySelectorAll<HTMLButtonElement>("button"))
      .at(-1)
      ?.focus({ preventScroll: true });
    return () => {
      for (const { element, inert } of background) element.inert = inert;
      document.documentElement.style.overflow = overflow;
      if (previous instanceof HTMLElement && previous.isConnected)
        previous.focus({ preventScroll: true });
    };
  }, []);
  return createPortal(
    <div className="task-notice-backdrop">
      <div
        ref={dialog}
        role="dialog"
        aria-modal="true"
        className="task-notice"
        aria-label={working ? "Processing PDF" : "PDF needs attention"}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.preventDefault();
            e.stopPropagation();
            close();
          } else if (e.key === "Tab") {
            const buttons = Array.from(
              e.currentTarget.querySelectorAll<HTMLButtonElement>(
                "button:not(:disabled)",
              ),
            );
            const first = buttons[0],
              last = buttons.at(-1);
            if (e.shiftKey && document.activeElement === first) {
              e.preventDefault();
              last?.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
              e.preventDefault();
              first?.focus();
            }
          }
        }}
      >
        <h2>
          {title ??
            (working ? "Preparing your PDF…" : "Your PDF was not created")}
        </h2>
        {working && <progress aria-label="PDF processing" />}
        <p role={working ? "status" : "alert"}>{message}</p>
        {!working && <p>Your source and draft are unchanged.</p>}
        {adjust && (
          <>
            <p>
              To continue, links and bookmarks pointing to excluded pages will
              keep their appearance and titles but lose their jumps.
              Destinations, tags and form fields belonging to excluded pages
              will be removed. Other content stays. Ambiguous structures may
              still be refused.
            </p>
            <button onClick={adjust}>
              Allow these adjustments and create PDF
            </button>
          </>
        )}
        <button className="secondary" onClick={close}>
          {working ? "Cancel processing" : "Back to editing"}
        </button>
      </div>
    </div>,
    document.body,
  );
}
