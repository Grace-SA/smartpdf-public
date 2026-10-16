// Set export density without decoding or recompressing image pixels.
export async function density(blob: Blob, dpi: 150 | 300) {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  if (blob.type === "image/jpeg") {
    if (bytes[0] !== 255 || bytes[1] !== 216) throw Error("BAD_JPEG");
    for (let at = 2; at + 4 < bytes.length;) {
      if (bytes[at] !== 255) throw Error("BAD_JPEG_MARKER");
      const marker = bytes[at + 1]!;
      if (marker === 218 || marker === 217) break;
      const length = (bytes[at + 2]! << 8) | bytes[at + 3]!;
      if (length < 2 || at + 2 + length > bytes.length)
        throw Error("BAD_JPEG_LENGTH");
      if (
        marker === 224 &&
        length >= 16 &&
        String.fromCharCode(...bytes.slice(at + 4, at + 9)) === "JFIF\0"
      ) {
        bytes[at + 11] = 1;
        bytes[at + 12] = dpi >> 8;
        bytes[at + 13] = dpi & 255;
        bytes[at + 14] = dpi >> 8;
        bytes[at + 15] = dpi & 255;
        return new Blob([bytes], { type: blob.type });
      }
      at += length + 2;
    }
    const jfif = new Uint8Array([
      255,
      224,
      0,
      16,
      74,
      70,
      73,
      70,
      0,
      1,
      2,
      1,
      dpi >> 8,
      dpi & 255,
      dpi >> 8,
      dpi & 255,
      0,
      0,
    ]);
    return new Blob([bytes.slice(0, 2), jfif, bytes.slice(2)], {
      type: blob.type,
    });
  }
  if (
    blob.type !== "image/png" ||
    bytes.slice(0, 8).join() !== "137,80,78,71,13,10,26,10"
  )
    throw Error("BAD_PNG");
  const chunk = new Uint8Array(21),
    v = new DataView(chunk.buffer);
  v.setUint32(0, 9);
  chunk.set([112, 72, 89, 115], 4);
  const metres = Math.round(dpi / 0.0254);
  v.setUint32(8, metres);
  v.setUint32(12, metres);
  chunk[16] = 1;
  let crc = 0xffffffff;
  for (const b of chunk.slice(4, 17)) {
    crc ^= b;
    for (let bit = 0; bit < 8; bit++)
      crc = crc & 1 ? 0xedb88320 ^ (crc >>> 1) : crc >>> 1;
  }
  v.setUint32(17, (crc ^ 0xffffffff) >>> 0);
  const parts: BlobPart[] = [bytes.slice(0, 8)];
  let inserted = false;
  for (let at = 8; at + 12 <= bytes.length;) {
    const length = new DataView(bytes.buffer).getUint32(at),
      end = at + length + 12;
    if (end > bytes.length) throw Error("BAD_PNG_LENGTH");
    const name = String.fromCharCode(...bytes.slice(at + 4, at + 8));
    if (name !== "pHYs") parts.push(bytes.slice(at, end));
    if (name === "IHDR") {
      parts.push(chunk);
      inserted = true;
    }
    at = end;
  }
  if (!inserted) throw Error("NO_IHDR");
  return new Blob(parts, { type: blob.type });
}
