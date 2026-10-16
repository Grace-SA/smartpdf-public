import {
  PDFDict,
  PDFDocument,
  PDFName,
  PDFNumber,
  PDFRawStream,
  PDFRef,
  decodePDFRawStream,
} from "pdf-lib";
import { LIMITS } from "../core/contracts";
import type { CompressionLevel } from "./model";

const k = PDFName.of;
const MIN_DIMENSION = 256;
const MIN_AREA = 65_536;
const MIN_STREAM_BYTES = 64 * 1024;
const MAX_TOTAL_PIXELS = 20_000_000;

export type RgbJpegEncoder = (
  rgb: Uint8Array,
  width: number,
  height: number,
  quality: number,
) => Promise<Uint8Array>;

function number(dict: PDFDict, name: string): number | undefined {
  const value = dict.context.lookup(dict.get(k(name)));
  return value instanceof PDFNumber ? value.asNumber() : undefined;
}

function name(dict: PDFDict, key: string): PDFName | undefined {
  const value = dict.context.lookup(dict.get(k(key)));
  return value instanceof PDFName ? value : undefined;
}

function paeth(a: number, b: number, c: number) {
  const p = a + b - c;
  const pa = Math.abs(p - a);
  const pb = Math.abs(p - b);
  const pc = Math.abs(p - c);
  return pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
}

/** Undo the PNG row filters used by PDF Flate image predictors 10–15. */
export function undoPngPredictor(
  input: Uint8Array,
  width: number,
  height: number,
  colors = 3,
): Uint8Array {
  const rowBytes = width * colors;
  if (input.length !== (rowBytes + 1) * height)
    throw new Error("Unexpected PNG predictor length.");
  const output = new Uint8Array(rowBytes * height);
  for (let y = 0; y < height; y += 1) {
    const sourceStart = y * (rowBytes + 1);
    const targetStart = y * rowBytes;
    const filter = input[sourceStart]!;
    if (filter > 4) throw new Error("Unsupported PNG predictor filter.");
    for (let x = 0; x < rowBytes; x += 1) {
      const raw = input[sourceStart + 1 + x]!;
      const left = x >= colors ? output[targetStart + x - colors]! : 0;
      const up = y > 0 ? output[targetStart - rowBytes + x]! : 0;
      const upLeft =
        y > 0 && x >= colors ? output[targetStart - rowBytes + x - colors]! : 0;
      const value =
        filter === 0
          ? raw
          : filter === 1
            ? raw + left
            : filter === 2
              ? raw + up
              : filter === 3
                ? raw + Math.floor((left + up) / 2)
                : raw + paeth(left, up, upLeft);
      output[targetStart + x] = value & 0xff;
    }
  }
  return output;
}

function decodedRgb(stream: PDFRawStream, width: number, height: number) {
  const parms = stream.dict.context.lookup(stream.dict.get(k("DecodeParms")));
  let predictor = 1;
  if (parms !== undefined) {
    if (!(parms instanceof PDFDict)) return undefined;
    const allowed = new Set([
      "Predictor",
      "Colors",
      "BitsPerComponent",
      "Columns",
    ]);
    if (parms.keys().some((key) => !allowed.has(key.decodeText())))
      return undefined;
    predictor = number(parms, "Predictor") ?? 1;
    if (
      (number(parms, "Colors") ?? 3) !== 3 ||
      (number(parms, "BitsPerComponent") ?? 8) !== 8 ||
      (number(parms, "Columns") ?? width) !== width
    )
      return undefined;
  }
  let bytes: Uint8Array;
  try {
    bytes = decodePDFRawStream(stream).decode();
  } catch {
    return undefined;
  }
  if (predictor === 1)
    return bytes.length === width * height * 3 ? bytes : undefined;
  if (predictor < 10 || predictor > 15) return undefined;
  try {
    return undoPngPredictor(bytes, width, height);
  } catch {
    return undefined;
  }
}

export type ImageRecompressionResult = {
  bytes: Uint8Array;
  replacedImages: number;
};

/**
 * Re-encodes only ordinary 8-bit DeviceRGB Flate images. The image object and
 * any SMask reference stay in place, so page content, links, forms, tags and
 * transparency structure are not rebuilt. Unsupported images remain untouched.
 */
export async function recompressCommonImages(
  source: Uint8Array,
  level: CompressionLevel,
  encode: RgbJpegEncoder,
): Promise<ImageRecompressionResult> {
  if (level === "quality") return { bytes: source, replacedImages: 0 };
  const doc = await PDFDocument.load(source, {
    updateMetadata: false,
    throwOnInvalidObject: true,
  });
  const objects = doc.context.enumerateIndirectObjects();
  const maskRefs = new Set<string>();
  for (const [, object] of objects) {
    if (!(object instanceof PDFRawStream)) continue;
    const mask = object.dict.get(k("SMask"));
    if (mask instanceof PDFRef) maskRefs.add(mask.toString());
  }

  let replacedImages = 0;
  let processedPixels = 0;
  const quality = level === "smaller" ? 0.65 : 0.8;
  for (const [ref, object] of objects) {
    if (!(object instanceof PDFRawStream) || maskRefs.has(ref.toString()))
      continue;
    const dict = object.dict;
    const width = number(dict, "Width");
    const height = number(dict, "Height");
    const pixels = (width ?? 0) * (height ?? 0);
    if (
      name(dict, "Subtype") !== k("Image") ||
      name(dict, "Filter") !== k("FlateDecode") ||
      name(dict, "ColorSpace") !== k("DeviceRGB") ||
      number(dict, "BitsPerComponent") !== 8 ||
      dict.has(k("ImageMask")) ||
      dict.has(k("Mask")) ||
      dict.has(k("Decode")) ||
      !Number.isInteger(width) ||
      !Number.isInteger(height) ||
      width! < MIN_DIMENSION ||
      height! < MIN_DIMENSION ||
      pixels < MIN_AREA ||
      pixels > LIMITS.canvasPixels ||
      processedPixels + pixels > MAX_TOTAL_PIXELS ||
      object.contents.length < MIN_STREAM_BYTES
    )
      continue;
    const rgb = decodedRgb(object, width!, height!);
    if (!rgb) continue;
    processedPixels += pixels;
    let jpeg: Uint8Array;
    try {
      jpeg = await encode(rgb, width!, height!, quality);
    } catch {
      continue;
    }
    const minimumSaving = Math.max(
      1024,
      Math.ceil(object.contents.length * 0.05),
    );
    if (jpeg.length + minimumSaving >= object.contents.length) continue;
    const replacement = dict.clone();
    replacement.set(k("Filter"), k("DCTDecode"));
    replacement.delete(k("DecodeParms"));
    doc.context.assign(ref, PDFRawStream.of(replacement, jpeg));
    replacedImages += 1;
  }
  if (replacedImages === 0) return { bytes: source, replacedImages };
  return {
    bytes: await doc.save({
      useObjectStreams: true,
      updateFieldAppearances: false,
    }),
    replacedImages,
  };
}
