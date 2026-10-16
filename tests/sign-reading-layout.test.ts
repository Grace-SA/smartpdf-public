import { describe, it, expect } from "vitest";
import {
  readingLayout,
  readingPage,
  readingWindow,
} from "../src/sign/reading-layout";
import type { Geometry } from "../src/sign/model";
const page = (width: number, height: number, rotation = 0): Geometry => ({
  x: 0,
  y: 0,
  width,
  height,
  rotation,
  unit: 1,
});
describe("continuous document layout", () => {
  it("keeps portrait, landscape and rotated pages in one non-overlapping document", () => {
    const layout = readingLayout(
      [page(600, 800), page(800, 600), page(600, 800, 90)],
      600,
      400,
      1,
    );
    expect(layout.map((p) => p.height)).toEqual([800, 450, 450]);
    expect(layout[1]!.top).toBe(layout[0]!.top + 800 + 48);
    expect(readingPage(layout, layout[1]!.top + 100)).toBe(1);
    expect(readingPage(layout, 1e8)).toBe(2);
  });
  it("bounds live canvases even when 200 tiny pages fit on screen", () => {
    const layout = readingLayout(
      Array.from({ length: 200 }, () => page(2, 1)),
      600,
      600,
      1,
    );
    const active = readingWindow(layout, layout[80]!.top, 1000);
    expect(active.size).toBeLessThanOrEqual(5);
    const current = readingPage(layout, layout[80]!.top + 200);
    expect(active.has(current)).toBe(true);
    expect(active.has(0)).toBe(false);
  });
  it("retains a page-relative anchor across fit width, zoom and fit page", () => {
    const geometry = Array.from({ length: 100 }, () => page(600, 800));
    for (const zoom of [0.75, 1, 1.5, 2, -1]) {
      const layout = readingLayout(geometry, 300, 500, zoom);
      const position = layout[79]!.top + layout[79]!.height * 0.4;
      expect(readingPage(layout, position)).toBe(79);
      if (zoom === -1) expect(layout[79]!.height).toBeLessThanOrEqual(476);
    }
  });
});
