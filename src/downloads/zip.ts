import { readLocalFile } from "../platform/abort";

const table = new Uint32Array(256);
for (let n = 0; n < 256; n++) {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  table[n] = c >>> 0;
}

/** Store PDF bytes unchanged. Read one bounded slice at a time for CRC; Blob
 * parts reference the original files rather than allocating a second batch. */
export async function zipFiles(
  files: File[],
  options: { maxFiles?: number; maxBytes?: number; signal?: AbortSignal } = {},
): Promise<Blob> {
  const maxBytes = options.maxBytes ?? 60 * 1048576;
  if (
    !files.length ||
    files.length > Math.min(options.maxFiles ?? 50, 200) ||
    files.reduce((n, f) => n + f.size, 0) > maxBytes
  )
    throw new Error("Download exceeds the session limits.");
  const parts: BlobPart[] = [],
    central: Uint8Array<ArrayBuffer>[] = [];
  let offset = 0;
  const used = new Set<string>();
  const controller = new AbortController();
  const abort = () => controller.abort();
  options.signal?.addEventListener("abort", abort, { once: true });
  if (options.signal?.aborted) controller.abort();
  const check = () => {
    if (controller.signal.aborted) throw new Error("Download cancelled.");
  };
  const timeout = setTimeout(() => controller.abort(), 120000);
  try {
    for (const file of files) {
      check();
      // ZIP entry names must not contain path separators or control bytes.
      let name =
        [...file.name]
          .map((c) => (c.charCodeAt(0) < 32 || "/\\:".includes(c) ? "_" : c))
          .join("")
          .replace(/^\.+/, "_") || "document.pdf";
      const original = name;
      let i = 1;
      while (used.has(name.toLowerCase())) name = `${i++}-${original}`;
      used.add(name.toLowerCase());
      const encoded = new TextEncoder().encode(name);
      if (encoded.length > 65535) throw new Error("Filename too long.");
      let crc = 0xffffffff;
      for (let start = 0; start < file.size; start += 1048576) {
        const chunk = await readLocalFile(
          file.slice(start, start + 1048576),
          controller.signal,
        );
        for (const b of new Uint8Array(chunk))
          crc = table[(crc ^ b) & 255]! ^ (crc >>> 8);
        await new Promise<void>((resolve) => setTimeout(resolve, 0));
        check();
      }
      crc = (crc ^ 0xffffffff) >>> 0;
      const local = new Uint8Array(30 + encoded.length),
        l = new DataView(local.buffer);
      l.setUint32(0, 0x04034b50, true);
      l.setUint16(4, 20, true);
      l.setUint16(6, 0x800, true);
      l.setUint16(12, 0x21, true);
      l.setUint32(14, crc, true);
      l.setUint32(18, file.size, true);
      l.setUint32(22, file.size, true);
      l.setUint16(26, encoded.length, true);
      local.set(encoded, 30);
      parts.push(local, file);
      const header = new Uint8Array(46 + encoded.length),
        h = new DataView(header.buffer);
      h.setUint32(0, 0x02014b50, true);
      h.setUint16(4, 20, true);
      h.setUint16(6, 20, true);
      h.setUint16(8, 0x800, true);
      h.setUint16(14, 0x21, true);
      h.setUint32(16, crc, true);
      h.setUint32(20, file.size, true);
      h.setUint32(24, file.size, true);
      h.setUint16(28, encoded.length, true);
      h.setUint32(42, offset, true);
      header.set(encoded, 46);
      central.push(header);
      offset += local.length + file.size;
      if (
        offset + central.reduce((sum, h) => sum + h.length, 0) + 22 >
        maxBytes
      )
        throw new Error("Download exceeds the session limits.");
    }
    const end = new Uint8Array(22),
      e = new DataView(end.buffer);
    e.setUint32(0, 0x06054b50, true);
    e.setUint16(8, files.length, true);
    e.setUint16(10, files.length, true);
    e.setUint32(
      12,
      central.reduce((n, h) => n + h.length, 0),
      true,
    );
    e.setUint32(16, offset, true);
    check();
    return new Blob([...parts, ...central, end], { type: "application/zip" });
  } finally {
    options.signal?.removeEventListener("abort", abort);
    clearTimeout(timeout);
  }
}
