import { LIMITS, ProbeFailure } from "./contracts";

// Validate lossless image data without keeping a whole decoded image buffer.
// Feeding at most 4 KiB per pull also bounds output produced by each inflater
// transform, including highly compressible input. The output is never retained.
export async function checkFlateImage(
  bytes: Uint8Array,
  remainingWork: number = LIMITS.decodedImageBytes,
): Promise<number> {
  const stage = (value: string) =>
    Reflect.get(globalThis, "syntheticProbeStage")?.(value);
  stage("flate-enter");
  if (
    bytes.length < 6 ||
    (bytes[0]! & 15) !== 8 ||
    bytes[0]! >>> 4 > 7 ||
    ((bytes[0]! << 8) + bytes[1]!) % 31 !== 0 ||
    (bytes[1]! & 32) !== 0
  )
    throw new ProbeFailure("INVALID_INPUT", "malformed");
  let offset = 0;
  const input = new ReadableStream<BufferSource>({
    pull(controller) {
      if (offset === bytes.length) {
        controller.close();
        return;
      }
      const end = Math.min(offset + 4096, bytes.length);
      const chunk = bytes.slice(offset, end);
      // Some ordinary exporters understate the zlib window in CMF. PDF readers
      // decode these with the full 32 KiB window. Validate with that same bounded
      // window; keep the original compressed stream and Adler checksum untouched.
      if (offset === 0) {
        chunk[0] = 0x78;
        chunk[1] = bytes[1]! & 0xe0;
        chunk[1] += (31 - ((0x7800 + chunk[1]) % 31)) % 31;
      }
      controller.enqueue(chunk);
      offset = end;
    },
  });
  const reader = input
    .pipeThrough(new DecompressionStream("deflate"))
    .getReader();
  let decoded = 0;
  try {
    for (;;) {
      const chunk = await reader.read();
      if (chunk.done) {
        stage("flate-eof");
        return decoded;
      }
      decoded += chunk.value.byteLength;
      if (decoded > Math.min(LIMITS.decodedImageBytes, remainingWork))
        throw new ProbeFailure("RESOURCE_LIMIT", "complexity");
    }
  } finally {
    stage("flate-cancel");
    await reader.cancel().catch(() => {});
    stage("flate-cancelled");
    reader.releaseLock();
    stage("flate-released");
  }
}
