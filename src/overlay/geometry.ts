import { PDFName, PDFNumber, type PDFPage } from "pdf-lib";
export type Geometry = {
  x: number;
  y: number;
  width: number;
  height: number;
  rotation: number;
  unit: number;
};
export type Rect = { x: number; y: number; width: number; height: number };
export type Matrix = [number, number, number, number, number, number];
export function displaySize(g: Geometry) {
  const turn = g.rotation === 90 || g.rotation === 270;
  return {
    width: (turn ? g.height : g.width) * g.unit,
    height: (turn ? g.width : g.height) * g.unit,
  };
}
export function validGeometry(g: Geometry) {
  return (
    Object.values(g).every(Number.isFinite) &&
    g.width > 0 &&
    g.height > 0 &&
    g.unit > 0 &&
    [0, 90, 180, 270].includes(g.rotation)
  );
}
export function pageGeometry(page: PDFPage): Geometry {
  const m = page.getMediaBox(),
    c = page.getCropBox(),
    x = Math.max(m.x, c.x),
    y = Math.max(m.y, c.y);
  const g = {
    x,
    y,
    width: Math.min(m.x + m.width, c.x + c.width) - x,
    height: Math.min(m.y + m.height, c.y + c.height) - y,
    rotation: ((page.getRotation().angle % 360) + 360) % 360,
    unit:
      page.node.lookupMaybe(PDFName.of("UserUnit"), PDFNumber)?.asNumber() ?? 1,
  };
  if (!validGeometry(g)) throw Error("Unsupported page geometry.");
  return g;
}
/** Physical points from the visible top left, including CropBox, Rotate, UserUnit. */
export function displayPoint(
  g: Geometry,
  x: number,
  y: number,
): [number, number] {
  const u = x / g.unit,
    v = y / g.unit;
  switch (g.rotation) {
    case 0:
      return [g.x + u, g.y + g.height - v];
    case 90:
      return [g.x + v, g.y + u];
    case 180:
      return [g.x + g.width - u, g.y + v];
    case 270:
      return [g.x + g.width - v, g.y + g.height - u];
    default:
      throw Error("Unsupported page geometry.");
  }
}
export function pdfPoint(g: Geometry, x: number, y: number): [number, number] {
  const u = x - g.x,
    v = y - g.y;
  switch (g.rotation) {
    case 0:
      return [u * g.unit, (g.height - v) * g.unit];
    case 90:
      return [v * g.unit, u * g.unit];
    case 180:
      return [(g.width - u) * g.unit, v * g.unit];
    case 270:
      return [(g.height - v) * g.unit, (g.width - u) * g.unit];
    default:
      throw Error("Unsupported page geometry.");
  }
}
export function stampMatrix(
  g: Geometry,
  cx: number,
  cy: number,
  w: number,
  h: number,
  angle: number,
): Matrix {
  const r = (angle * Math.PI) / 180,
    c = Math.cos(r),
    s = Math.sin(r);
  const x = cx - (w * c) / 2 - (h * s) / 2,
    y = cy - (w * s) / 2 + (h * c) / 2;
  const p = displayPoint(g, x, y),
    px = displayPoint(g, x + c, y + s),
    py = displayPoint(g, x + s, y - c);
  return [px[0] - p[0], px[1] - p[1], py[0] - p[0], py[1] - p[1], p[0], p[1]];
}
