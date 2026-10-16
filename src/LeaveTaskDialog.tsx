import { useEffect, useRef } from "react";

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
  useEffect(() => {
    const previous = document.activeElement;
    const node = dialog.current!;
    node.showModal();
    keepButton.current?.focus();
    return () => {
      node.close();
      if (previous instanceof HTMLElement && previous.isConnected)
        previous.focus();
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
