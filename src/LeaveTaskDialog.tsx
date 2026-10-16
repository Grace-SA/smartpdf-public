import { useLayoutEffect, useRef } from "react";

export function LeaveTaskDialog({
  description,
  keep,
  leave,
}: {
  description: string;
  keep: () => void;
  leave: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const keepButton = useRef<HTMLButtonElement>(null);
  // Close the native modal before React detaches it. Passive cleanup can race
  // WebKit's own focus restoration when the detached dialog is removed.
  useLayoutEffect(() => {
    const previous = document.activeElement;
    const node = dialog.current!;
    node.showModal();
    keepButton.current?.focus({ preventScroll: true });
    return () => {
      node.close();
      if (previous instanceof HTMLElement && previous.isConnected)
        previous.focus({ preventScroll: true });
    };
  }, []);
  return (
    <dialog
      ref={dialog}
      className="leave-task-dialog"
      aria-labelledby="leave-task-title"
      aria-describedby="leave-task-description"
      onCancel={(event) => {
        event.preventDefault();
        keep();
      }}
    >
      <h2 id="leave-task-title">Leave this task?</h2>
      <p id="leave-task-description">
        {description} Your original files will not be deleted.
      </p>
      <div className="leave-task-actions">
        <button ref={keepButton} onClick={keep}>
          Keep editing
        </button>
        <button className="secondary" onClick={leave}>
          Discard task and leave
        </button>
      </div>
    </dialog>
  );
}
