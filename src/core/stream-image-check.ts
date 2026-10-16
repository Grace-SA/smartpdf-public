import { Inflate, type ZStream } from "pako";
import { LIMITS, ProbeFailure } from "./contracts";

// Validate and discard fixed-size decoded chunks in the probe worker. Avoid
// native stream scheduling/cleanup, which can stall WebKit's worker process.
export async function checkFlateImage(
  bytes: Uint8Array,
  remainingWork: number = LIMITS.decodedImageBytes,
): Promise<number> {
  if (
    bytes.length < 6 ||
    (bytes[0]! & 15) !== 8 ||
    bytes[0]! >>> 4 > 7 ||
    ((bytes[0]! << 8) + bytes[1]!) % 31 !== 0 ||
    (bytes[1]! & 32) !== 0
  )
    throw new ProbeFailure("INVALID_INPUT", "malformed");
  const inflater = new Inflate({ windowBits: 15, chunkSize: 64 * 1024 });
  let decoded = 0;
  let stream: ZStream | undefined;
  inflater.onStart = (value) => {
    stream = value;
  };
  inflater.onData = (chunk) => {
    decoded += chunk.byteLength;
    if (decoded > Math.min(LIMITS.decodedImageBytes, remainingWork))
      throw new ProbeFailure("RESOURCE_LIMIT", "complexity");
    // Do not call the default handler: it retains all decompressed chunks.
  };
  for (let offset = 0; offset < bytes.length; offset += 4096) {
    const end = Math.min(offset + 4096, bytes.length);
    const chunk = bytes.slice(offset, end);
    // Ordinary exporters sometimes understate the zlib window. Use the same
    // full 32 KiB window as PDF readers; still validate the original Adler sum.
    if (offset === 0) {
      chunk[0] = 0x78;
      chunk[1] = bytes[1]! & 0xe0;
      chunk[1] += (31 - ((0x7800 + chunk[1]) % 31)) % 31;
    }
    if (!inflater.push(chunk, end === bytes.length) || inflater.err)
      throw new ProbeFailure("INVALID_INPUT", "malformed");
    if (inflater.ended) {
      if (end !== bytes.length || stream?.total_in !== bytes.length)
        throw new ProbeFailure("INVALID_INPUT", "malformed");
      return decoded;
    }
  }
  throw new ProbeFailure("INVALID_INPUT", "malformed");
}
