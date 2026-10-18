import { LIMITS } from "../core/contracts";
import {
  displaySize,
  validGeometry,
  type Geometry,
  type Rect,
} from "../overlay/geometry";
import type { TextShape } from "../overlay/text";

export const positions = [
  "Top left",
  "Top center",
  "Top right",
  "Bottom left",
  "Bottom center",
  "Bottom right",
] as const;
export type NumberSettings = {
  mode: "all" | "skip-first" | "range";
  from: number;
  to: number;
  start: number;
  format: "number" | "fraction" | "page-total";
  position: number;
  size: number;
  margin: number;
  color: string;
};
export const defaults: NumberSettings = {
  mode: "all",
  from: 1,
  to: 1,
  start: 1,
  format: "number",
  position: 4,
  size: 12,
  margin: 10,
  color: "#000000",
};
export type NumberStamp = Rect & {
  page: number;
  value: number;
  text: string;
  shape: TextShape;
};
export type NumberPlan = {
  pages: number[];
  stamps: (NumberStamp | null)[];
  first: number;
  last: number;
};

export function numberPages(settings: NumberSettings, count: number) {
  if (!Number.isInteger(count) || count < 1 || count > LIMITS.pages)
    throw Error("Choose a PDF with 1–200 pages.");
  if (!["all", "skip-first", "range"].includes(settings.mode))
    throw Error("Choose which pages to number.");
  const first =
    settings.mode === "all"
      ? 1
      : settings.mode === "skip-first"
        ? 2
        : settings.from;
  const last = settings.mode === "range" ? settings.to : count;
  if (settings.mode === "skip-first" && count === 1)
    throw Error("There are no pages after the cover. Choose All pages.");
  if (
    !Number.isInteger(first) ||
    !Number.isInteger(last) ||
    first < 1 ||
    last > count ||
    first > last
  )
    throw Error(
      `Choose PDF pages from 1 to ${count}, with From no greater than To.`,
    );
  return Array.from({ length: last - first + 1 }, (_, i) => first - 1 + i);
}
export function numberText(
  value: number,
  last: number,
  format: NumberSettings["format"],
) {
  if (format === "fraction") return `${value} / ${last}`;
  if (format === "page-total") return `Page ${value} of ${last}`;
  return String(value);
}
export function planNumbers(
  settings: NumberSettings,
  geometry: Geometry[],
  measure: (text: string) => TextShape,
  annotations: Rect[][] = [],
): NumberPlan {
  const pages = numberPages(settings, geometry.length),
    last = settings.start + pages.length - 1;
  if (!Number.isInteger(settings.start) || settings.start < 1 || last > 999999)
    throw Error(
      "Choose a start number from 1 to 999999; the last number must also be at most 999999.",
    );
  if (!["number", "fraction", "page-total"].includes(settings.format))
    throw Error("Choose a page number format.");
  if (
    !Number.isInteger(settings.position) ||
    settings.position < 0 ||
    settings.position > 5 ||
    !Number.isFinite(settings.size) ||
    settings.size < 8 ||
    settings.size > 36 ||
    !Number.isFinite(settings.margin) ||
    settings.margin < 3 ||
    settings.margin > 30 ||
    !/^#[\da-f]{6}$/i.test(settings.color)
  )
    throw Error(
      "Choose a position, 8–36 pt size, 3–30 mm margin and valid color.",
    );
  const stamps: (NumberStamp | null)[] = geometry.map(() => null);
  for (const [ordinal, page] of pages.entries()) {
    const g = geometry[page]!;
    if (!validGeometry(g))
      throw Error(`PDF page ${page + 1} has unsupported geometry.`);
    const value = settings.start + ordinal,
      text = numberText(value, last, settings.format),
      shape = measure(text),
      scale = settings.size / shape.units;
    const width = shape.width * scale,
      height = shape.height * scale,
      margin = (settings.margin * 72) / 25.4,
      size = displaySize(g);
    if (
      ![width, height].every((n) => Number.isFinite(n) && n > 0) ||
      width + 2 * margin > size.width ||
      height + 2 * margin > size.height
    )
      throw Error(
        `Page ${page + 1} is too small for these numbers. Reduce the size or margin.`,
      );
    const column = settings.position % 3;
    const x =
      column === 0
        ? margin
        : column === 1
          ? (size.width - width) / 2
          : size.width - margin - width;
    const y = settings.position < 3 ? margin : size.height - margin - height;
    if (
      annotations[page]?.some(
        (r) =>
          x < r.x + r.width - 0.001 &&
          x + width > r.x + 0.001 &&
          y < r.y + r.height - 0.001 &&
          y + height > r.y + 0.001,
      )
    )
      throw Error(
        `Page ${page + 1}: the number overlaps a visible form field or annotation. Choose another position or margin.`,
      );
    stamps[page] = { page, value, text, shape, x, y, width, height };
  }
  return { pages, stamps, first: settings.start, last };
}
