import fontkit from "@pdf-lib/fontkit";
import { normalizedText, WATERMARK_LIMITS } from "./model";
let resource: Promise<Uint8Array> | null = null;
export function prepareWatermark(signal: AbortSignal) {
  if (!resource)
    resource = fetch("/watermark-fonts/SmartPDFSans-Regular.ttf", { signal })
      .then(async (response) => {
        if (!response.ok)
          throw Error("The watermark font could not load. Retry this tool.");
        const bytes = new Uint8Array(await response.arrayBuffer());
        if (bytes.length > WATERMARK_LIMITS.fontBytes)
          throw Error("The watermark font exceeds its budget.");
        return bytes;
      })
      .catch((error) => {
        resource = null;
        throw error;
      });
  return resource;
}
export type TextShape = {
  text: string;
  width: number;
  height: number;
  left: number;
  bottom: number;
  top: number;
  units: number;
  paths: { x: number; d: string }[];
};
let fontBytes: Uint8Array | undefined,
  face: ReturnType<typeof fontkit.create> | undefined;
export function watermarkFont(bytes: Uint8Array) {
  if (bytes !== fontBytes) {
    face = fontkit.create(bytes);
    fontBytes = bytes;
  }
  return face!;
}
export function textShape(bytes: Uint8Array, value: string): TextShape {
  const text = normalizedText(value),
    font = watermarkFont(bytes);
  const missing = [
    ...new Set(
      [...text].filter((c) => !font.hasGlyphForCodePoint(c.codePointAt(0)!)),
    ),
  ];
  if (missing.length)
    throw Error(
      `The watermark font does not support: ${missing.slice(0, 8).join(" ")}. Use supported text or an image watermark.`,
    );
  const glyphs = font.layout(text).glyphs;
  let x = 0,
    left = 0,
    right = 0,
    bottom = Infinity,
    top = -Infinity;
  const paths: { x: number; d: string }[] = [];
  for (const glyph of glyphs) {
    const box = glyph.bbox;
    if (box.maxX > box.minX && box.maxY > box.minY) {
      left = Math.min(left, x + box.minX);
      right = Math.max(right, x + box.maxX);
      bottom = Math.min(bottom, box.minY);
      top = Math.max(top, box.maxY);
      paths.push({ x, d: glyph.path.toSVG() });
    }
    x += glyph.advanceWidth;
  }
  right = Math.max(right, x);
  if (!paths.length || !Number.isFinite(top - bottom) || right <= left)
    throw Error("Enter visible watermark text.");
  return {
    text,
    width: right - left,
    height: top - bottom,
    left,
    bottom,
    top,
    units: font.unitsPerEm,
    paths,
  };
}
