import type { createWordService } from "../word/service.mjs";
type Service = Awaited<ReturnType<typeof createWordService>>;
export function createOfficeServices(options?: {
  word?: Parameters<typeof createWordService>[0];
  ppt?: Parameters<typeof createWordService>[0];
  pdfword?: Parameters<typeof createWordService>[0];
}): Promise<{
  word: Service;
  ppt: Service;
  pdfword?: Service;
  close: () => Promise<void>;
}>;
