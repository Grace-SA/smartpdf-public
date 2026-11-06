export function createOfficeAdmission(options: {
  pauseWord: () => Promise<void> | undefined;
  resumeWord: () => void | Promise<void>;
}): {
  available: () => boolean;
  fail: () => void;
  acquire: (
    kind: "word" | "ppt",
    signal: AbortSignal,
  ) => Promise<(healthy?: boolean) => Promise<void>>;
  close: () => void;
};
