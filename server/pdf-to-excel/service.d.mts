import type { Server } from "node:http";
export function createPdfExcelService(options?: {
  python?: string;
  ttlMs?: number;
  tempRoot?: string;
  timeoutMs?: number;
  origin?: string;
  ocr?: boolean;
  secureCookies?: boolean;
  run?: (
    job: { dir: string; options: Record<string, unknown> },
    context: { signal: AbortSignal },
  ) => Promise<unknown>;
}): Promise<{ server: Server; root: string; close: () => Promise<void> }>;
