import type { createWordService } from "../word/service.mjs";
export function createPdfWordService(
  options?: Parameters<typeof createWordService>[0],
): ReturnType<typeof createWordService>;
