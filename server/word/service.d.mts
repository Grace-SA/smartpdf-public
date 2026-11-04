import type { Server } from "node:http";
export type Task = {
  id: string;
  kind?: "word" | "excel";
  directory: string;
  state: string;
  owner: string;
  expiresAt: number;
  error?: string;
};
export function checkPdf(file: string): Promise<{ pages: number }>;
export function createWordService(options?: {
  root?: string;
  enableExcel?: boolean;
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
