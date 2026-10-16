let signatureSequence = 0;
export const newSignatureId = () => `signature-${++signatureSequence}`;
export const SIGN_LIMITS = {
  instances: 100,
  assets: 20,
  imageBytes: 5 * 1024 * 1024,
  pixels: 4_000_000,
  totalBytes: 20 * 1024 * 1024,
  nameLength: 120,
  points: 20000,
} as const;
import { displaySize, validGeometry, type Geometry } from "../overlay/geometry";
export { displaySize, validGeometry, type Geometry } from "../overlay/geometry";
export type SignatureAsset = {
  id: string;
  bytes: Uint8Array;
  width: number;
  height: number;
  url: string;
};
export type Placement = {
  id: string;
  asset: string;
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
};
export function fits(p: Placement, g: Geometry) {
  const s = displaySize(g);
  return (
    validGeometry(g) &&
    [p.x, p.y, p.width, p.height].every(Number.isFinite) &&
    p.width > 0 &&
    p.height > 0 &&
    p.x >= 0 &&
    p.y >= 0 &&
    p.x + p.width <= s.width + 0.001 &&
    p.y + p.height <= s.height + 0.001
  );
}
export function constrain(p: Placement, g: Geometry): Placement {
  const s = displaySize(g),
    factor = Math.min(1, s.width / p.width, s.height / p.height);
  const width = p.width * factor,
    height = p.height * factor;
  return {
    ...p,
    width,
    height,
    x: Math.max(0, Math.min(p.x, s.width - width)),
    y: Math.max(0, Math.min(p.y, s.height - height)),
  };
}
/** Display coordinates are physical PDF points, measured from the visible top left. */
export function imageTransform(p: Placement, g: Geometry) {
  if (!fits(p, g)) throw Error("Keep the whole signature inside the page.");
  const l = p.x / g.unit,
    t = p.y / g.unit,
    w = p.width / g.unit,
    h = p.height / g.unit;
  const origins: Record<number, [number, number]> = {
    0: [g.x + l, g.y + g.height - t - h],
    90: [g.x + t + h, g.y + l],
    180: [g.x + g.width - l, g.y + t + h],
    270: [g.x + g.width - t - h, g.y + g.height - l],
  };
  const [x, y] = origins[g.rotation]!;
  return { x, y, width: w, height: h, angle: g.rotation };
}
