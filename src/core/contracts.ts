export const LIMITS = {
  bytes: 30 * 1024 * 1024,
  pages: 200,
  objects: 50_000,
  nodes: 200_000,
  depth: 100,
  imagePixels: 16_000_000,
  jpegPixels: 24_000_000,
  canvasPixels: 4_000_000,
  pagePoints: 14_400,
  metadataBytes: 1024 * 1024,
  decodedStreamBytes: 8 * 1024 * 1024,
  decodedImageBytes: 32 * 1024 * 1024,
  streamedImageWorkBytes: 512 * 1024 * 1024,
  timeoutMs: 120_000,
} as const;

export type ErrorCode =
  | "INVALID_INPUT"
  | "UNSUPPORTED_PDF"
  | "RESOURCE_LIMIT"
  | "PROCESSING_FAILED"
  | "CANCELLED"
  | "TIMEOUT";
export type Reason =
  | "encrypted"
  | "signature"
  | "form"
  | "annotations"
  | "attachments"
  | "actions"
  | "layers"
  | "navigation"
  | "tagged"
  | "standard"
  | "multimedia"
  | "malformed"
  | "missingReference"
  | "size"
  | "pages"
  | "complexity"
  | "geometry"
  | "image"
  | "inlineImage";
export type ProbeResult =
  | { ok: true; pages: number; byteLength: number; previewFeatures?: Reason[] }
  | { ok: false; code: ErrorCode; reason?: Reason; reasons?: Reason[] };
export class ProbeFailure extends Error {
  constructor(
    public readonly code: ErrorCode,
    public readonly reason?: Reason,
    public readonly reasons?: Reason[],
  ) {
    super(code);
  }
}
export function validateSize(size: number): void {
  if (!Number.isSafeInteger(size) || size < 1)
    throw new ProbeFailure("INVALID_INPUT", "size");
  if (size > LIMITS.bytes) throw new ProbeFailure("RESOURCE_LIMIT", "size");
}
export function failure(error: unknown): Extract<ProbeResult, { ok: false }> {
  return error instanceof ProbeFailure
    ? { ok: false, code: error.code, reason: error.reason }
    : { ok: false, code: "INVALID_INPUT", reason: "malformed" };
}
