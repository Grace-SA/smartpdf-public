export function isHeic(bytes: Uint8Array): boolean {
  if (bytes.length < 16) return false;
  const text = (p: number) => String.fromCharCode(...bytes.subarray(p, p + 4));
  if (text(4) !== "ftyp") return false;
  const end = new DataView(
    bytes.buffer,
    bytes.byteOffset,
    bytes.byteLength,
  ).getUint32(0);
  if (end < 16 || end > bytes.length || end > 4096 || end % 4) return false;
  for (let p = 8; p < end; p += p === 8 ? 8 : 4)
    if (["heic", "heix", "hevc", "hevx", "mif1", "msf1"].includes(text(p)))
      return true;
  return false;
}
