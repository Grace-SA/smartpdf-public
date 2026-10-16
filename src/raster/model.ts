import { pageRange } from "../organize/range";
import { safeFilename } from "../photos/model";
export type ImageFormat = "jpg" | "png";
export type Dpi = 150 | 300;
export const RASTER = {
  pixels: 10_000_000,
  side: 4096,
  bytes: 60 * 1048576,
} as const;
export type RasterResult = { file: File; count: number; format: ImageFormat };
export const selectedPages = (range: string | null, count: number) =>
  range === null
    ? Array.from({ length: count }, (_, i) => i)
    : pageRange(range, count);
export function dimensions(width: number, height: number) {
  const round = (n: number) =>
    Math.abs(n - Math.round(n)) < 1e-7 ? Math.round(n) : Math.ceil(n);
  const w = round(width),
    h = round(height);
  if (
    !Number.isSafeInteger(w) ||
    !Number.isSafeInteger(h) ||
    w < 1 ||
    h < 1 ||
    w > RASTER.side ||
    h > RASTER.side ||
    w * h > RASTER.pixels
  )
    throw new Error(
      "This page is too large at this quality. Use Standard or choose a smaller page range.",
    );
  return { width: w, height: h };
}
export function imageName(source: string, page: number, format: ImageFormat) {
  const base =
    safeFilename(source.replace(/\.pdf$/i, ""))
      .replace(/\.pdf$/i, "")
      .slice(0, 100) || "document";
  return `${base}-page-${String(page).padStart(3, "0")}.${format}`;
}
export const archiveName = (name: string) =>
  `${
    safeFilename(name.replace(/\.pdf$/i, ""))
      .replace(/\.pdf$/i, "")
      .slice(0, 100) || "document"
  }-images.zip`;
