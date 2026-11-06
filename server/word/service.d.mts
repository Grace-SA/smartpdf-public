import type { Server } from "node:http";
export type Task = {
  id: string;
  directory: string;
  state: string;
  owner: string;
  expiresAt: number;
  error?: string;
  options?: {
    revisionView: "unchanged" | "final" | "original";
    omitComments: boolean;
    useAvailableFonts?: boolean;
  };
};
export function checkPdf(
  file: string,
  policy?: { ppt: boolean; visible: number; width: number; height: number },
): Promise<{ pages: number }>;
export function createWordService(options?: {
  format?: "word" | "ppt";
  root?: string;
  origin?: string;
  now?: () => number;
  admit?: (
    job: Task,
    signal: AbortSignal,
  ) => Promise<(healthy?: boolean) => Promise<void>>;
  available?: () => boolean;
  onUnsafe?: () => void;
  execute?: (
    job: Task,
    update: (value: { state?: string; warnings?: string[] }) => void,
  ) => Promise<void>;
  validate?: (file: string) => Promise<{ pages: number }>;
}): Promise<{
  server: Server;
  jobs: Map<string, Task>;
  sweep: () => Promise<void>;
  pauseStandby: () => Promise<void> | undefined;
  resumeStandby: () => void;
  close: () => Promise<void>;
}>;
