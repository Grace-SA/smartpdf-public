export const PHOTO_LIMITS = {
  count: 20,
  fileBytes: 15 * 1024 * 1024,
  pixels: 16_000_000,
  inputBytes: 50 * 1024 * 1024,
  sessionBytes: 60 * 1024 * 1024,
  timeoutMs: 120_000,
} as const;
export type ImageInfo = {
  format: "jpeg" | "png";
  width: number;
  height: number;
  orientation: number;
};
export type PhotoSettings = {
  paper: "A4" | "Letter";
  direction: "auto" | "portrait" | "landscape";
};
export const defaultSettings: PhotoSettings = {
  paper: "A4",
  direction: "auto",
};
export const photoCopy = {
  invalid: "Choose a complete JPEG, PNG or supported HEIC still image.",
  large: "Each image must be at most 15 MiB and 16 megapixels.",
  budget:
    "This would exceed the 60 MiB task budget. Use fewer or smaller files.",
  total: "Use at most 20 images and 50 MiB in this photo task.",
  failed: "The PDF could not be created. Your previous document is unchanged.",
  low: "Low resolution: this image may look blurry in print.",
};
// Read dimensions before a browser or PNG decoder allocates pixel storage.
export function inspectImage(bytes: Uint8Array): ImageInfo {
  if (!bytes.length || bytes.length > PHOTO_LIMITS.fileBytes)
    throw new Error(photoCopy.large);
  const v = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const text = (offset: number, length: number) =>
    String.fromCharCode(...bytes.subarray(offset, offset + length));
  const exif = (offset: number, end: number): number => {
    if (end - offset < 8) throw new Error(photoCopy.invalid);
    const le = text(offset, 2) === "II";
    if (!le && text(offset, 2) !== "MM") throw new Error(photoCopy.invalid);
    const u16 = (n: number) => {
      if (n < offset || n + 2 > end) throw new Error(photoCopy.invalid);
      return v.getUint16(n, le);
    };
    const u32 = (n: number) => {
      if (n < offset || n + 4 > end) throw new Error(photoCopy.invalid);
      return v.getUint32(n, le);
    };
    if (u16(offset + 2) !== 42) throw new Error(photoCopy.invalid);
    const ifd = offset + u32(offset + 4),
      count = u16(ifd);
    if (ifd + 2 + count * 12 + 4 > end) throw new Error(photoCopy.invalid);
    for (let i = 0; i < count; i++) {
      const entry = ifd + 2 + 12 * i;
      if (u16(entry) === 274) {
        if (u16(entry + 2) !== 3 || u32(entry + 4) !== 1)
          throw new Error(photoCopy.invalid);
        const orientation = u16(entry + 8);
        if (orientation < 1 || orientation > 8)
          throw new Error(photoCopy.invalid);
        return orientation;
      }
    }
    return 1;
  };
  let width = 0,
    height = 0,
    orientation = 1;
  let format: ImageInfo["format"];
  if (
    bytes.length >= 33 &&
    [...bytes.subarray(0, 8)].join() === "137,80,78,71,13,10,26,10"
  ) {
    format = "png";
    if (text(12, 4) !== "IHDR" || v.getUint32(8) !== 13)
      throw new Error(photoCopy.invalid);
    width = v.getUint32(16);
    height = v.getUint32(20);
    let endFound = false;
    for (let p = 8; p + 12 <= bytes.length;) {
      const size = v.getUint32(p),
        end = p + size + 12;
      if (end > bytes.length) throw new Error(photoCopy.invalid);
      const kind = text(p + 4, 4);
      if (kind === "acTL")
        throw new Error(
          "Animated PNG is not supported. Choose a still JPEG or PNG.",
        );
      if (kind === "eXIf") orientation = exif(p + 8, p + 8 + size);
      if (kind === "IEND") {
        endFound = true;
        break;
      }
      p = end;
    }
    if (!endFound) throw new Error(photoCopy.invalid);
  } else if (bytes[0] === 255 && bytes[1] === 216) {
    format = "jpeg";
    if (bytes.at(-2) !== 255 || bytes.at(-1) !== 217)
      throw new Error(photoCopy.invalid);
    for (let p = 2; p + 4 <= bytes.length;) {
      if (bytes[p++] !== 255) throw new Error(photoCopy.invalid);
      while (bytes[p] === 255) p++;
      const marker = bytes[p++];
      if (marker === 218 || marker === 217) break;
      if (marker === 1 || (marker! >= 208 && marker! <= 215)) continue;
      const size = v.getUint16(p),
        end = p + size;
      if (size < 2 || end > bytes.length) throw new Error(photoCopy.invalid);
      if (marker === 225 && text(p + 2, 6) === "Exif\0\0")
        orientation = exif(p + 8, end);
      if ([192, 193, 194].includes(marker!)) {
        if (size < 8) throw new Error(photoCopy.invalid);
        height = v.getUint16(p + 3);
        width = v.getUint16(p + 5);
      }
      p = end;
    }
  } else throw new Error(photoCopy.invalid);
  if (!width || !height) throw new Error(photoCopy.invalid);
  if (width * height > PHOTO_LIMITS.pixels) throw new Error(photoCopy.large);
  return { format, width, height, orientation };
}
export type Matrix = [number, number, number, number, number, number];
const exifMatrices: Matrix[] = [
  [1, 0, 0, 1, 0, 0],
  [1, 0, 0, 1, 0, 0],
  [-1, 0, 0, 1, 1, 0],
  [-1, 0, 0, -1, 1, 1],
  [1, 0, 0, -1, 0, 1],
  [0, -1, -1, 0, 1, 1],
  [0, -1, 1, 0, 0, 1],
  [0, 1, 1, 0, 0, 0],
  [0, 1, -1, 0, 1, 0],
];
export function layout(
  info: ImageInfo,
  turns: number,
  settings: PhotoSettings,
) {
  let m = [...exifMatrices[info.orientation]!] as Matrix;
  let width = info.orientation >= 5 ? info.height : info.width;
  let height = info.orientation >= 5 ? info.width : info.height;
  for (let i = 0; i < ((turns % 4) + 4) % 4; i++) {
    const [a, b, c, d, e, f] = m;
    m = [b, -a, d, -c, f, 1 - e];
    [width, height] = [height, width];
  }
  const landscape =
    settings.direction === "landscape" ||
    (settings.direction === "auto" && width > height);
  const paper =
    settings.paper === "Letter" ? [612, 792] : [595.275590551, 841.88976378];
  const pw = paper[landscape ? 1 : 0]!,
    ph = paper[landscape ? 0 : 1]!;
  const margin = (10 * 72) / 25.4;
  const scale = Math.min((pw - 2 * margin) / width, (ph - 2 * margin) / height);
  const w = width * scale,
    h = height * scale,
    x = (pw - w) / 2,
    y = (ph - h) / 2;
  return {
    width: pw,
    height: ph,
    ppi: 72 / scale,
    matrix: [
      w * m[0],
      h * m[1],
      w * m[2],
      h * m[3],
      x + w * m[4],
      y + h * m[5],
    ] as Matrix,
  };
}
export function safeFilename(value: string): string {
  const base =
    Array.from(value, (c) =>
      c.charCodeAt(0) < 32 || c.charCodeAt(0) === 127 ? "_" : c,
    )
      .join("")
      .replace(/[/\\:*?"<>|]/g, "_")
      .replace(/[ .]+$/g, "")
      .slice(0, 160) || "Photos";
  return /\.pdf$/i.test(base) ? base : `${base}.pdf`;
}
