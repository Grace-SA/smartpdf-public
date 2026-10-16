import { displaySize, type Geometry } from "./model";
export type SheetLayout = { top: number; width: number; height: number };
export function readingLayout(
  geometry: Geometry[],
  width: number,
  height: number,
  zoom: number,
): SheetLayout[] {
  let top = 20;
  return geometry.map((g) => {
    const size = displaySize(g);
    const scale = Math.min(
      3,
      zoom === -1
        ? Math.min(width / size.width, Math.max(100, height - 24) / size.height)
        : (width / size.width) * zoom,
    );
    const sheet = {
      top,
      width: size.width * scale,
      height: size.height * scale,
    };
    top += sheet.height + 48;
    return sheet;
  });
}
export function readingPage(layout: SheetLayout[], position: number) {
  let index = 0;
  for (let i = 1; i < layout.length && layout[i]!.top <= position; i++)
    index = i;
  return index;
}
export function readingWindow(
  layout: SheetLayout[],
  scrollTop: number,
  height: number,
) {
  const center = readingPage(layout, scrollTop + Math.min(height * 0.28, 200));
  // Bound full-size canvases even for a document containing many tiny pages.
  return new Set(
    layout
      .map((_, i) => i)
      .filter(
        (i) =>
          layout[i]!.top + layout[i]!.height + 24 >= scrollTop - height &&
          layout[i]!.top <= scrollTop + height * 2,
      )
      .sort((a, b) => Math.abs(a - center) - Math.abs(b - center))
      .slice(0, 5),
  );
}
