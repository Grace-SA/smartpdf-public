import { test, expect } from "vitest";
import {
  PDFDocument,
  StandardFonts,
  degrees,
  PDFName,
  PDFNumber,
  rgb,
} from "pdf-lib";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import {
  combinePdfs,
  inspectPdf,
  validateInputs,
} from "../src/combine/generate";
const folder = "tests/fixtures/combine";
async function input(label: string, count: number) {
  const doc = await PDFDocument.create();
  const font = await doc.embedFont(StandardFonts.Helvetica);
  for (let i = 0; i < count; i++) {
    const p = doc.addPage(i % 2 ? [792, 612] : [595.2756, 841.8898]);
    p.drawText(`${label}-${i + 1} searchable text`, {
      x: 65,
      y: 90,
      size: 18,
      font,
    });
    p.drawRectangle({
      x: 60,
      y: 150,
      width: 80,
      height: 50,
      color: rgb(0.2, 0.5, 0.8),
    });
    if (label === "B") {
      p.setRotation(degrees(i * 90));
      p.setCropBox(20, 30, p.getWidth() - 40, p.getHeight() - 60);
    }
    if (label === "C") {
      p.setMediaBox(-10, -20, 612, 792);
      p.setCropBox(0, 0, 580, 750);
      p.node.set(PDFName.of("UserUnit"), PDFNumber.of(1.5));
    }
  }
  return doc.save();
}
test("COMBINE-01/02 copies 3+1+2 mixed pages and persists independent verification fixtures", async () => {
  const a = await input("A", 2),
    b = await input("B", 3),
    c = await input("C", 1);
  const order = [b, c, a],
    progress: number[] = [];
  const result = await combinePdfs(order, (n) => progress.push(n));
  expect(progress).toEqual([1, 2, 3]);
  const output = await PDFDocument.load(result);
  expect(output.getPageCount()).toBe(6);
  let offset = 0;
  for (const bytes of order) {
    const source = await PDFDocument.load(bytes);
    for (const page of source.getPages()) {
      const copy = output.getPage(offset++);
      expect(copy.getMediaBox()).toEqual(page.getMediaBox());
      expect(copy.getCropBox()).toEqual(page.getCropBox());
      expect(copy.getRotation()).toEqual(page.getRotation());
      expect(copy.node.get(PDFName.of("UserUnit"))?.toString()).toEqual(
        page.node.get(PDFName.of("UserUnit"))?.toString(),
      );
    }
  }
  await mkdir(folder, { recursive: true });
  await mkdir("docs/private-samples/m2", { recursive: true });
  for (const [name, bytes] of [
    ["a", a],
    ["b", b],
    ["c", c],
  ] as const)
    await writeFile(`${folder}/${name}.pdf`, bytes);
  await writeFile("docs/private-samples/m2/mixed.pdf", result);
});
test("rejects unsafe batch before copying and retains strict preview-only exclusions", async () => {
  const good = await input("A", 1);
  for (const name of [
    "tagged",
    "pdfa",
    "layers",
    "form",
    "signature",
    "javascript",
    "owner-encrypted",
  ]) {
    const bad = new Uint8Array(await readFile(`tests/fixtures/${name}.pdf`));
    expect((await inspectPdf(bad)).ok).toBe(false);
    const progress: number[] = [];
    await expect(
      combinePdfs([good, bad], (n) => progress.push(n)),
    ).rejects.toThrow();
    expect(progress).toEqual([]);
  }
});
test("aggregate count bytes and page limits fail without partial success", async () => {
  expect(() => validateInputs([])).toThrow();
  expect(() => validateInputs([new Uint8Array(1)])).toThrow();
  expect(() =>
    validateInputs(Array.from({ length: 11 }, () => new Uint8Array(1))),
  ).toThrow();
  expect(() =>
    validateInputs([new Uint8Array(30 * 1024 * 1024), new Uint8Array(1)]),
  ).toThrow();
  const doc = await PDFDocument.create();
  for (let n = 0; n < 101; n++) doc.addPage();
  const bytes = await doc.save();
  await expect(combinePdfs([bytes, bytes], () => {})).rejects.toThrow(
    "200 pages",
  );
});
test("same bytes entered twice remain distinct inputs and double page count", async () => {
  const bytes = await input("D", 2);
  const merged = await PDFDocument.load(
    await combinePdfs([bytes, bytes], () => {}),
  );
  expect(merged.getPageCount()).toBe(4);
});
