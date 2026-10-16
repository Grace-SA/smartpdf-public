import { displaySize, type Geometry, type Rect } from "../overlay/geometry";
import { pageRange } from "../organize/range";
export const WATERMARK_LIMITS = {
  imageBytes: 5 * 1024 * 1024,
  pixels: 4_000_000,
  fontBytes: 12 * 1024 * 1024,
  textLength: 120,
  perPage: 200,
  instances: 10_000,
};
export type WatermarkSettings = {
  type: "text" | "image";
  text: string;
  color: string;
  layout: "single" | "repeat";
  size: number;
  opacity: number;
  angle: number;
  position: number;
  spacing: "tight" | "normal" | "wide";
  range: string | null;
};
export const defaults: WatermarkSettings = {
  type: "text",
  text: "CONFIDENTIAL",
  color: "#555555",
  layout: "single",
  size: 50,
  opacity: 30,
  angle: -45,
  position: 4,
  spacing: "normal",
  range: null,
};
export type Stamp = {
  cx: number;
  cy: number;
  width: number;
  height: number;
  angle: number;
};
export type WatermarkPlan = {
  pages: number[];
  stamps: Stamp[][];
  count: number;
};
export function normalizedText(text: string) {
  const value = text.normalize("NFC").trim();
  if (
    !value ||
    [...value].length > WATERMARK_LIMITS.textLength ||
    /[\p{Cc}\p{Cf}\p{Cs}\p{Co}\p{M}]/u.test(value)
  )
    throw Error(
      "Enter one line of 1–120 supported characters. Combining marks and control characters are not supported.",
    );
  return value;
}
export function selectedWatermarkPages(
  settings: WatermarkSettings,
  count: number,
) {
  return settings.range === null
    ? Array.from({ length: count }, (_, i) => i)
    : pageRange(settings.range, count);
}
function overlaps(stamp: Stamp, rect: Rect) {
  const a = (stamp.angle * Math.PI) / 180,
    c = Math.cos(a),
    s = Math.sin(a);
  const points = [
    [-0.5, -0.5],
    [0.5, -0.5],
    [0.5, 0.5],
    [-0.5, 0.5],
  ].map(([x, y]) => [
    stamp.cx + x! * stamp.width * c - y! * stamp.height * s,
    stamp.cy + x! * stamp.width * s + y! * stamp.height * c,
  ]);
  const r = [
    [rect.x, rect.y],
    [rect.x + rect.width, rect.y],
    [rect.x + rect.width, rect.y + rect.height],
    [rect.x, rect.y + rect.height],
  ];
  for (const [x, y] of [
    [1, 0],
    [0, 1],
    [c, s],
    [-s, c],
  ]) {
    const p = points.map((v) => v[0]! * x! + v[1]! * y!),
      q = r.map((v) => v[0]! * x! + v[1]! * y!);
    if (
      Math.max(...p) <= Math.min(...q) + 0.001 ||
      Math.max(...q) <= Math.min(...p) + 0.001
    )
      return false;
  }
  return true;
}
export function planWatermarks(
  settings: WatermarkSettings,
  geometry: Geometry[],
  ratio: number,
  annotations: Rect[][] = [],
): WatermarkPlan {
  if (
    !["text", "image"].includes(settings.type) ||
    !["single", "repeat"].includes(settings.layout) ||
    !/^#[\da-f]{6}$/i.test(settings.color) ||
    ![
      settings.size,
      settings.opacity,
      settings.angle,
      settings.position,
      ratio,
    ].every(Number.isFinite) ||
    settings.size < 10 ||
    settings.size > 80 ||
    settings.opacity < 10 ||
    settings.opacity > 100 ||
    Math.abs(settings.angle) > 90 ||
    !Number.isInteger(settings.position) ||
    settings.position < 0 ||
    settings.position > 8 ||
    !["tight", "normal", "wide"].includes(settings.spacing) ||
    ratio <= 0
  )
    throw Error("Choose valid watermark settings.");
  const pages = selectedWatermarkPages(settings, geometry.length);
  if (!pages.length) throw Error("Choose at least one page.");
  const stamps: Stamp[][] = geometry.map(() => []);
  let count = 0;
  for (const index of pages) {
    const page = displaySize(geometry[index]!);
    const margin = Math.min(18, page.width * 0.04, page.height * 0.04),
      iw = page.width - 2 * margin,
      ih = page.height - 2 * margin;
    let w = (page.width * settings.size) / 100,
      h = w / ratio;
    const a = (settings.angle * Math.PI) / 180,
      c = Math.abs(Math.cos(a)),
      s = Math.abs(Math.sin(a));
    const scale = Math.min(1, iw / (w * c + h * s), ih / (w * s + h * c));
    w *= scale;
    h *= scale;
    const bw = w * c + h * s,
      bh = w * s + h * c;
    if (Math.min(w, h) < 0.01)
      throw Error(`Page ${index + 1} is too small for this watermark.`);
    const put = (cx: number, cy: number) => {
      const stamp = { cx, cy, width: w, height: h, angle: settings.angle };
      if ((annotations[index] ?? []).some((rect) => overlaps(stamp, rect)))
        throw Error(
          `The watermark on page ${index + 1} overlaps a form field or comment. Move it, reduce its size, or change the page range.`,
        );
      stamps[index]!.push(stamp);
    };
    if (settings.layout === "single") {
      const col = settings.position % 3,
        row = Math.floor(settings.position / 3);
      put(
        [margin + bw / 2, page.width / 2, page.width - margin - bw / 2][col]!,
        [margin + bh / 2, page.height / 2, page.height - margin - bh / 2][row]!,
      );
      count++;
    } else {
      const gap = { tight: 0.25, normal: 0.65, wide: 1.25 }[settings.spacing];
      const gx = Math.max(margin, bw * gap),
        gy = Math.max(margin, bh * gap);
      const cols = Math.max(1, Math.floor((iw + gx) / (bw + gx))),
        rows = Math.max(1, Math.floor((ih + gy) / (bh + gy)));
      const n = cols * rows;
      if (
        n > WATERMARK_LIMITS.perPage ||
        count + n > WATERMARK_LIMITS.instances
      )
        throw Error(
          "This repeat pattern creates too many watermarks. Increase size or spacing, or choose fewer pages.",
        );
      const left = (page.width - cols * bw - (cols - 1) * gx) / 2 + bw / 2,
        top = (page.height - rows * bh - (rows - 1) * gy) / 2 + bh / 2;
      for (let row = 0; row < rows; row++)
        for (let col = 0; col < cols; col++)
          put(left + col * (bw + gx), top + row * (bh + gy));
      count += n;
    }
  }
  return { pages, stamps, count };
}
