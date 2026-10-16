import { expect, it } from "vitest";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { PDFDocument } from "pdf-lib";
import {
  inspectImage,
  layout,
  defaultSettings,
  safeFilename,
  PHOTO_LIMITS,
} from "../src/photos/model";
import { generatePhotos } from "../src/photos/generate";
const fixture = async (name: string) =>
  new Uint8Array(await readFile(`tests/fixtures/photos/${name}`));
it("reads all eight EXIF orientations and generates an independent-review PDF", async () => {
  const inputs = [];
  for (let n = 1; n <= 8; n++) {
    const bytes = await fixture(`exif-${n}.jpg`);
    const info = inspectImage(bytes);
    expect(info).toEqual({
      format: "jpeg",
      width: 120,
      height: 80,
      orientation: n,
    });
    const l = layout(info, 0, defaultSettings);
    expect(l.width > l.height).toBe(n < 5);
    inputs.push({ bytes, turns: 0 });
  }
  const bytes = await generatePhotos(inputs, defaultSettings, () => {});
  const doc = await PDFDocument.load(bytes);
  expect(doc.getPageCount()).toBe(8);
  await mkdir("docs/private-samples/m1", { recursive: true });
  await writeFile("docs/private-samples/m1/exif-eight.pdf", bytes);
});
it("generates Letter pages with full images and 10mm margins after rotation", async () => {
  const bytes = await fixture("corners.png");
  const info = inspectImage(bytes);
  const settings = { paper: "Letter", direction: "portrait" } as const;
  const l = layout(info, 1, settings);
  expect([l.width, l.height]).toEqual([612, 792]);
  const [a, b, c, d, e, f] = l.matrix;
  const corners = [
    [0, 0],
    [1, 0],
    [0, 1],
    [1, 1],
  ].map(([x, y]) => [a * x! + c * y! + e, b * x! + d * y! + f]);
  for (const [x, y] of corners) {
    expect(x).toBeGreaterThanOrEqual(28.346);
    expect(y).toBeGreaterThanOrEqual(28.346);
    expect(x).toBeLessThanOrEqual(612 - 28.346);
    expect(y).toBeLessThanOrEqual(792 - 28.346);
  }
  const output = await generatePhotos(
    [
      { bytes, turns: 1 },
      { bytes: await fixture("alpha.png"), turns: 0 },
    ],
    settings,
    () => {},
  );
  expect(
    (await PDFDocument.load(output)).getPages().map((p) => p.getSize()),
  ).toEqual([
    { width: 612, height: 792 },
    { width: 612, height: 792 },
  ]);
  await mkdir("docs/private-samples/m1", { recursive: true });
  await writeFile("docs/private-samples/m1/letter-rotation-alpha.pdf", output);
});
it("rejects disguised, truncated and huge-dimension images before decoding", async () => {
  expect(() => inspectImage(new Uint8Array([1, 2, 3]))).toThrow();
  const png = await fixture("corners.png");
  expect(() => inspectImage(png.slice(0, -12))).toThrow();
  const huge = png.slice();
  new DataView(huge.buffer).setUint32(16, 16_000_001);
  expect(() => inspectImage(huge)).toThrow(/megapixels/);
  expect(() =>
    inspectImage(new Uint8Array(PHOTO_LIMITS.fileBytes + 1)),
  ).toThrow(/MiB/);
});
it("has empty and count limits and safe Unicode filenames", async () => {
  await expect(generatePhotos([], defaultSettings, () => {})).rejects.toThrow();
  const image = { bytes: await fixture("red.jpg"), turns: 0 };
  await expect(
    generatePhotos(
      Array.from({ length: 21 }, () => image),
      defaultSettings,
      () => {},
    ),
  ).rejects.toThrow();
  expect(safeFilename("合同/照片\u0000")).toBe("合同_照片_.pdf");
  expect(safeFilename("")).toBe("Photos.pdf");
  expect(safeFilename("中文.PDF")).toBe("中文.PDF");
});
