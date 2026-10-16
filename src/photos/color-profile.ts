import { PDFDocument, PDFName, PDFRawStream, type PDFImage } from "pdf-lib";

const LIMIT = 1024 * 1024;
const invalid = () =>
  new Error(
    "This image's color settings cannot be preserved. Export an sRGB image and try again.",
  );
const text = (b: Uint8Array, p: number, n: number) =>
  String.fromCharCode(...b.subarray(p, p + n));
async function inflate(bytes: Uint8Array): Promise<Uint8Array> {
  const reader = new Blob([bytes as Uint8Array<ArrayBuffer>])
    .stream()
    .pipeThrough(new DecompressionStream("deflate"))
    .getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      size += value.length;
      if (size > LIMIT) throw invalid();
      chunks.push(value);
    }
  } finally {
    await reader.cancel();
  }
  const result = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    result.set(chunk, offset);
    offset += chunk.length;
  }
  return result;
}
export type ImageColor =
  | { icc: Uint8Array; channels: number }
  | { gamma: number; white: number[]; matrix: number[] };
function iccProfile(icc: Uint8Array, channels: number): ImageColor {
  if (icc.length < 132 || icc.length > LIMIT) throw invalid();
  const v = new DataView(icc.buffer, icc.byteOffset, icc.byteLength);
  if (
    v.getUint32(0) !== icc.length ||
    text(icc, 36, 4) !== "acsp" ||
    text(icc, 16, 4) !==
      ({ 1: "GRAY", 3: "RGB ", 4: "CMYK" } as Record<number, string>)[
        channels
      ] ||
    !["XYZ ", "Lab "].includes(text(icc, 20, 4))
  )
    throw invalid();
  const count = v.getUint32(128);
  if (!count || count > 256 || 132 + count * 12 > icc.length) throw invalid();
  for (let i = 0; i < count; i++) {
    const start = v.getUint32(136 + i * 12),
      length = v.getUint32(140 + i * 12);
    if (start < 132 + count * 12 || length < 8 || start + length > icc.length)
      throw invalid();
  }
  return { icc, channels };
}
// Convert PNG chromaticities to the column-major matrix required by PDF CalRGB.
function calibrated(
  gamma: number,
  chroma = [0.3127, 0.329, 0.64, 0.33, 0.3, 0.6, 0.15, 0.06],
): ImageColor {
  if (!Number.isFinite(gamma) || gamma <= 0 || gamma > 10) throw invalid();
  const xyz = (x: number, y: number) => {
    if (x < 0 || y <= 0 || x + y > 1.00001) throw invalid();
    return [x / y, 1, (1 - x - y) / y];
  };
  const white = xyz(chroma[0]!, chroma[1]!);
  const columns = [2, 4, 6].map((i) => xyz(chroma[i]!, chroma[i + 1]!));
  const rows = [0, 1, 2].map((i) => [...columns.map((c) => c[i]!), white[i]!]);
  for (let i = 0; i < 3; i++) {
    let pivot = i;
    for (let j = i + 1; j < 3; j++)
      if (Math.abs(rows[j]![i]!) > Math.abs(rows[pivot]![i]!)) pivot = j;
    [rows[i], rows[pivot]] = [rows[pivot]!, rows[i]!];
    const divisor = rows[i]![i]!;
    if (Math.abs(divisor) < 1e-8) throw invalid();
    rows[i] = rows[i]!.map((x) => x / divisor);
    for (let j = 0; j < 3; j++)
      if (j !== i) {
        const factor = rows[j]![i]!;
        rows[j] = rows[j]!.map((x, k) => x - factor * rows[i]![k]!);
      }
  }
  const matrix = columns.flatMap((c, i) => c.map((x) => x * rows[i]![3]!));
  if (
    matrix.some((x) => !Number.isFinite(x) || x < -0.00001) ||
    rows.some((r) => r[3]! <= 0)
  )
    throw invalid();
  return { gamma, white, matrix };
}
export async function inspectImageColor(
  bytes: Uint8Array,
  format: "jpeg" | "png",
): Promise<ImageColor | undefined> {
  const v = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (format === "jpeg") {
    const pieces = new Map<number, Uint8Array>();
    let total = 0,
      channels = 0,
      size = 0;
    for (let p = 2; p + 4 <= bytes.length;) {
      if (bytes[p++] !== 255) throw invalid();
      while (bytes[p] === 255) p++;
      const marker = bytes[p++];
      if (marker === 218 || marker === 217) break;
      if (marker === 1 || (marker! >= 208 && marker! <= 215)) continue;
      const length = v.getUint16(p),
        end = p + length;
      if (length < 2 || end > bytes.length) throw invalid();
      if ([192, 193, 194].includes(marker!)) channels = bytes[p + 7]!;
      if (marker === 226 && text(bytes, p + 2, 12) === "ICC_PROFILE\0") {
        if (length < 16) throw invalid();
        const index = bytes[p + 14]!,
          count = bytes[p + 15]!;
        if (
          !index ||
          index > count ||
          (total && count !== total) ||
          pieces.has(index)
        )
          throw invalid();
        total = count;
        const piece = bytes.subarray(p + 16, end);
        size += piece.length;
        if (size > LIMIT) throw invalid();
        pieces.set(index, piece);
      }
      p = end;
    }
    if (!pieces.size) return;
    if (pieces.size !== total) throw invalid();
    const profile = new Uint8Array(size);
    let offset = 0;
    for (let i = 1; i <= total; i++) {
      const part = pieces.get(i)!;
      profile.set(part, offset);
      offset += part.length;
    }
    return iccProfile(profile, channels);
  }
  let profile: Uint8Array | undefined,
    gamma: number | undefined,
    chroma: number[] | undefined,
    srgb = false;
  const seen = new Set<string>();
  for (let p = 8; p + 12 <= bytes.length;) {
    const size = v.getUint32(p),
      end = p + size + 12,
      kind = text(bytes, p + 4, 4),
      data = p + 8;
    if (end > bytes.length) throw invalid();
    if (
      ["iCCP", "sRGB", "gAMA", "cHRM", "cICP", "mDCV", "cLLI"].includes(kind)
    ) {
      if (seen.has(kind)) throw invalid();
      seen.add(kind);
    }
    if (kind === "iCCP") {
      const nameEnd = bytes.indexOf(0, data);
      if (
        nameEnd <= data ||
        nameEnd - data > 79 ||
        nameEnd + 2 >= data + size ||
        bytes[nameEnd + 1] !== 0
      )
        throw invalid();
      profile = await inflate(bytes.subarray(nameEnd + 2, data + size));
    } else if (kind === "gAMA") {
      if (size !== 4 || !v.getUint32(data)) throw invalid();
      gamma = 100000 / v.getUint32(data);
    } else if (kind === "cHRM") {
      if (size !== 32) throw invalid();
      chroma = Array.from(
        { length: 8 },
        (_, i) => v.getUint32(data + 4 * i) / 100000,
      );
    } else if (kind === "sRGB") {
      if (size !== 1 || bytes[data]! > 3) throw invalid();
      srgb = true;
    } else if (kind === "cICP" || kind === "mDCV" || kind === "cLLI")
      throw invalid();
    if (kind === "IEND") break;
    p = end;
  }
  if (profile && srgb) throw invalid();
  // pdf-lib expands PNG samples to RGB, including indexed and grayscale PNGs.
  if (profile) return iccProfile(profile, 3);
  if (srgb) return;
  if (gamma !== undefined) return calibrated(gamma, chroma);
  if (chroma) throw invalid(); // No transfer curve is supplied; do not invent one.
}
export async function preserveImageColor(
  doc: PDFDocument,
  image: PDFImage,
  color: ImageColor | undefined,
) {
  if (!color) return;
  await image.embed();
  const stream = doc.context.lookup(image.ref);
  if (!(stream instanceof PDFRawStream)) throw invalid();
  if ("icc" in color) {
    const profile = doc.context.register(
      doc.context.flateStream(color.icc, { N: color.channels }),
    );
    stream.dict.set(
      PDFName.of("ColorSpace"),
      doc.context.obj(["ICCBased", profile]),
    );
  } else {
    stream.dict.set(
      PDFName.of("ColorSpace"),
      doc.context.obj([
        "CalRGB",
        {
          WhitePoint: color.white,
          Gamma: [color.gamma, color.gamma, color.gamma],
          Matrix: color.matrix,
        },
      ]),
    );
  }
}
