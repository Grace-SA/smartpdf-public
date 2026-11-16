import type { Server } from "node:http";
export type Task = {
  id: string;
  kind?: "word" | "excel" | "ppt" | "pdfword";
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
  policyOrKind?:
    | "word"
    | "excel"
    | "ppt"
    | { ppt: boolean; visible: number; width: number; height: number },
): Promise<{ pages: number }>;
export function createWordService(options?: {
  format?: "word" | "ppt" | "pdfword";
  region?: string;
  root?: string;
  enableExcel?: boolean;
  origin?: string;
  now?: () => number;
  admit?: (
    job: Task,
    signal: AbortSignal,
  ) => Promise<(healthy?: boolean) => Promise<void>>;
  available?: () => boolean;
  capabilities?: Record<string, unknown>;
  processingTtlMs?: number;
  onUnsafe?: () => void;
  execute?: (
    job: Task,
    update: (value: { state?: string; warnings?: string[] }) => void,
  ) => Promise<void>;
  validate?: (
    file: string,
    kind?: "word" | "excel" | "ppt" | "pdfword",
  ) => Promise<{ pages: number }>;
}): Promise<{
  server: Server;
  jobs: Map<string, Task>;
  sweep: () => Promise<void>;
  pauseStandby: () => Promise<void> | undefined;
  resumeStandby: () => void;
  close: () => Promise<void>;
}>;
