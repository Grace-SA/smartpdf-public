import fontkit from "@pdf-lib/fontkit";

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
const faces = new WeakMap<Uint8Array, ReturnType<typeof fontkit.create>>();
export function glyphShape(bytes: Uint8Array, text: string): TextShape {
  let face = faces.get(bytes);
  if (!face) {
    face = fontkit.create(bytes);
    faces.set(bytes, face);
  }
  const missing = [
    ...new Set(
      [...text].filter((c) => !face.hasGlyphForCodePoint(c.codePointAt(0)!)),
    ),
  ];
  if (missing.length)
    throw Error(`The font does not support: ${missing.slice(0, 8).join(" ")}.`);
  let x = 0,
    left = 0,
    right = 0,
    bottom = Infinity,
    top = -Infinity;
  const paths: TextShape["paths"] = [];
  for (const glyph of face.layout(text).glyphs) {
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
    throw Error("Enter visible text.");
  return {
    text,
    width: right - left,
    height: top - bottom,
    left,
    bottom,
    top,
    units: face.unitsPerEm,
    paths,
  };
}
export function glyphSvg(shape: TextShape, color: string) {
  if (!/^#[\da-f]{6}$/i.test(color)) throw Error("Choose a valid text color.");
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${shape.width} ${shape.height}"><g fill="${color}" transform="translate(${-shape.left} ${shape.top}) scale(1 -1)">${shape.paths.map((p) => `<path transform="translate(${p.x} 0)" d="${p.d}"/>`).join("")}</g></svg>`;
  return "data:image/svg+xml," + encodeURIComponent(svg);
}
