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
export function checkPdf(file: string): Promise<{ pages: number }>;
export function createWordService(options?: {
  root?: string;
  origin?: string;
  now?: () => number;
  execute?: (
    job: Task,
    update: (value: { state?: string; warnings?: string[] }) => void,
  ) => Promise<void>;
  validate?: (file: string) => Promise<{ pages: number }>;
}): Promise<{
  server: Server;
  jobs: Map<string, Task>;
  sweep: () => Promise<void>;
  close: () => Promise<void>;
}>;
