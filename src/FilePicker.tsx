import type { ChangeEvent, Ref } from "react";

/** The native input itself receives the tap, including on iOS after navigation. */
export function FilePicker({
  id,
  children,
  disabled,
  accept,
  multiple,
  inputRef,
  onChange,
}: {
  id: string;
  children: string;
  disabled: boolean;
  accept: string;
  multiple?: boolean;
  inputRef?: Ref<HTMLInputElement>;
  onChange: (event: ChangeEvent<HTMLInputElement>) => void;
}) {
  return (
    <label
      className="file-label native-file-picker"
      htmlFor={id}
      aria-disabled={disabled}
    >
      <span>{children}</span>
      <input
        ref={inputRef}
        id={id}
        type="file"
        data-task-source="true"
        accept={accept}
        multiple={multiple}
        disabled={disabled}
        onChange={onChange}
      />
    </label>
  );
}
