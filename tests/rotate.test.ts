import { expect, test } from "vitest";
import {
  PDFArray,
  PDFDocument,
  PDFName,
  PDFRawStream,
  PDFNumber,
  decodePDFRawStream,
} from "pdf-lib";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { turnPages } from "../src/rotate/model";
import { rotatePdf, rotateErrors } from "../src/rotate/generate";
const root = "tests/fixtures/m5/";
const outputDir = "docs/evidence/m7-output";

test("M7 preserves ordinary ICC output intents without stripping color information", async () => {
  const source = new Uint8Array(
    await readFile("tests/fixtures/combine/final-color.pdf"),
  );
  const before = await PDFDocument.load(source, { updateMetadata: false });
  const after = await PDFDocument.load(
    await rotatePdf(
      source,
      before.getPages().map(() => 1),
    ),
    { updateMetadata: false },
  );
  expect(before.catalog.get(PDFName.of("OutputIntents"))).toBeDefined();
  expect(after.catalog.toString()).toBe(before.catalog.toString());
});

test("rotation targets are unique, relative and immutable; four turns and left/right cancel", () => {
  const original = [0, 1, 2, 3];
  expect(turnPages(original, [0, 0, 2], 1)).toEqual([1, 1, 3, 3]);
  expect(original).toEqual([0, 1, 2, 3]);
  expect(turnPages(turnPages(original, [1], -1), [1], 1)).toEqual(original);
  let turns = original;
  for (let i = 0; i < 4; i++) turns = turnPages(turns, [0, 1, 2, 3], 1);
  expect(turns).toEqual(original);
  expect(() => turnPages(original, [4], 1)).toThrow();
  expect(() => turnPages(original, [-1], 1)).toThrow();
  expect(() => turnPages([NaN], [0], 1)).toThrow();
});

const names = [
  "normal-a4",
  "mixed-page-size",
  "landscape",
  "100-pages",
  "scanned",
  "form",
  "chinese",
  "japanese",
  "image-heavy",
  "200-pages",
  "unusual-page-sizes",
];
for (const name of names)
  test(`M7 fixed regression: ${name}.pdf preserves content, geometry and page identity`, async () => {
    const source = new Uint8Array(await readFile(root + name + ".pdf"));
    const hash = createHash("sha256").update(source).digest("hex");
    const before = await PDFDocument.load(source, { updateMetadata: false });
    const turns = before.getPages().map((_, i) => (i % 3) + 1);
    const bytes = await rotatePdf(source, turns);
    const after = await PDFDocument.load(bytes, { updateMetadata: false });
    expect(after.getPageCount()).toBe(before.getPageCount());
    expect(after.catalog.toString()).toBe(before.catalog.toString());
    for (const [i, page] of after.getPages().entries()) {
      const original = before.getPage(i);
      expect(page.ref.toString()).toBe(original.ref.toString());
      expect(page.getRotation().angle).toBe(
        (((original.getRotation().angle + turns[i]! * 90) % 360) + 360) % 360,
      );
      expect(page.getMediaBox()).toEqual(original.getMediaBox());
      expect(page.getCropBox()).toEqual(original.getCropBox());
      for (const key of [
        "Contents",
        "Resources",
        "Annots",
        "StructParents",
        "UserUnit",
      ])
        expect(page.node.get(PDFName.of(key))?.toString()).toBe(
          original.node.get(PDFName.of(key))?.toString(),
        );
      const contents = (doc: PDFDocument, index: number) => {
        const value = doc.getPage(index).node.lookup(PDFName.of("Contents"));
        const streams =
          value instanceof PDFArray
            ? value.asArray().map((ref) => doc.context.lookup(ref))
            : [value];
        return streams.map((stream) =>
          stream instanceof PDFRawStream
            ? Buffer.from(decodePDFRawStream(stream).decode()).toString("hex")
            : String(stream),
        );
      };
      expect(contents(after, i)).toEqual(contents(before, i));
    }
    expect(createHash("sha256").update(source).digest("hex")).toBe(hash);
    await mkdir(outputDir, { recursive: true });
    await writeFile(`${outputDir}/${name}-rotated.pdf`, bytes);
  }, 60000);

for (const name of [
  "encrypted",
  "corrupted",
  "large-50mb",
  "zero-pages",
  "100mb",
])
  test(`M7 edge safely refuses ${name}`, async () => {
    await expect(
      rotatePdf(new Uint8Array(await readFile(root + name + ".pdf")), [1]),
    ).rejects.toThrow();
  });

test("M7 rejects incomplete, no-change and non-quarter-turn plans", async () => {
  const source = new Uint8Array(await readFile(root + "normal-a4.pdf"));
  const n = (await PDFDocument.load(source)).getPageCount();
  for (const turns of [
    [],
    Array(n).fill(0),
    Array(n).fill(4),
    Array(n).fill(-1),
    Array(n).fill(1.5),
    Array(n).fill(NaN),
    Array(n + 1).fill(1),
  ])
    await expect(rotatePdf(source, turns)).rejects.toThrow(
      rotateErrors.invalid,
    );
});

test("M7 preserves inherited rotation, cropped/offset pages and UserUnit", async () => {
  const doc = await PDFDocument.create();
  const page = doc.addPage([420, 600]);
  page.drawText("Geometry anchor", { x: 40, y: 80 });
  page.setCropBox(20, 40, 300, 450);
  page.node.set(PDFName.of("UserUnit"), PDFNumber.of(2));
  doc.catalog.Pages().set(PDFName.of("Rotate"), PDFNumber.of(270));
  page.node.delete(PDFName.of("Rotate"));
  const source = await doc.save();
  const output = await PDFDocument.load(await rotatePdf(source, [1]));
  expect(output.getPage(0).getRotation().angle).toBe(0);
  expect(output.getPage(0).getCropBox()).toEqual({
    x: 20,
    y: 40,
    width: 300,
    height: 450,
  });
  expect(output.getPage(0).node.get(PDFName.of("UserUnit"))?.toString()).toBe(
    "2",
  );
  await mkdir(outputDir, { recursive: true });
  await writeFile(`${outputDir}/geometry-source.pdf`, source);
  await writeFile(
    `${outputDir}/geometry-rotated.pdf`,
    await rotatePdf(source, [1]),
  );
});

for (const name of [
  "navigation-a",
  "tag-a",
  "layer-on",
  "layer-off",
  "ordinary-comments",
  "final-form",
  "ordinary-tagged-link",
  "optional-tag-indexes",
])
  test(`M7 retains supported navigation, tags, layers or annotations: ${name}`, async () => {
    const source = new Uint8Array(
      await readFile(`tests/fixtures/combine/${name}.pdf`),
    );
    const before = await PDFDocument.load(source, { updateMetadata: false });
    const bytes = await rotatePdf(
      source,
      before.getPages().map(() => 1),
    );
    const after = await PDFDocument.load(bytes, { updateMetadata: false });
    expect(after.catalog.toString()).toBe(before.catalog.toString());
    expect(after.getPages().map((page) => page.ref.toString())).toEqual(
      before.getPages().map((page) => page.ref.toString()),
    );
    await mkdir(outputDir, { recursive: true });
    await writeFile(`${outputDir}/structure-${name}-source.pdf`, source);
    await writeFile(`${outputDir}/structure-${name}-rotated.pdf`, bytes);
  });
