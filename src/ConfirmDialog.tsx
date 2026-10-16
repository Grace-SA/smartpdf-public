import { useLayoutEffect, useRef, type ReactNode } from "react";

export function ConfirmDialog({
  title,
  onCancel,
  children,
  cancelLabel = "Stay here",
  action,
}: {
  title: string;
  onCancel: () => void;
  children: ReactNode;
  cancelLabel?: string;
  action: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useLayoutEffect(() => {
    const dialog = ref.current!;
    const previous = document.activeElement;
    dialog.showModal();
    dialog
      .querySelector<HTMLButtonElement>("[data-stay]")
      ?.focus({ preventScroll: true });
    return () => {
      dialog.close();
      if (previous instanceof HTMLElement && previous.isConnected)
        previous.focus({ preventScroll: true });
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="draft-dialog"
      aria-label={title}
      aria-modal="true"
      onCancel={(event) => {
        event.preventDefault();
        onCancel();
      }}
    >
      <h2>{title}</h2>
      <div className="confirmation-content">{children}</div>
      <div className="confirmation-actions">
        <button data-stay className="secondary" onClick={onCancel}>
          {cancelLabel}
        </button>
        {action}
      </div>
    </dialog>
  );
}
