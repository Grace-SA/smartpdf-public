import { describe, it, expect } from "vitest";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import {
  PDFDocument,
  PDFName,
  PDFNumber,
  PDFDict,
  PDFString,
  StandardFonts,
  rgb,
} from "pdf-lib";
import {
  defaults,
  planWatermarks,
  normalizedText,
} from "../src/watermark/model";
import { watermarkPdf, inspectWatermark } from "../src/watermark/generate";
import { textShape } from "../src/watermark/font";
import {
  displaySize,
  displayPoint,
  pdfPoint,
  stampMatrix,
  type Geometry,
} from "../src/overlay/geometry";
const font = new Uint8Array(
  await readFile("public/watermark-fonts/SmartPDFSans-Regular.ttf"),
);
const folder = "docs/evidence/m10-output";
await mkdir(folder, { recursive: true });
const root = "tests/fixtures/m5/";
describe("watermark geometry and settings", () => {
  const geometry: Geometry[] = [0, 90, 180, 270].flatMap((rotation) =>
    [1, 2].map((unit) => ({
      x: 47,
      y: 83,
      width: 320,
      height: 510,
      rotation,
      unit,
    })),
  );
  it("maps visible physical coordinates both ways and stamps into the original coordinate space", () => {
    for (const g of geometry)
      for (const [x, y] of [
        [0, 0],
        [100, 50],
        [displaySize(g).width, displaySize(g).height],
      ]) {
        const p = displayPoint(g, x!, y!),
          q = pdfPoint(g, ...p);
        expect(q[0]).toBeCloseTo(x!);
        expect(q[1]).toBeCloseTo(y!);
        const m = stampMatrix(g, x!, y!, 60, 20, 0),
          origin = pdfPoint(g, m[4], m[5]);
        expect(origin[0]).toBeCloseTo(x! - 30);
        expect(origin[1]).toBeCloseTo(y! + 10);
      }
  });
  it("keeps all rotated single positions and repeated marks wholly inside mixed visible pages", () => {
    for (const angle of [-90, -45, 0, 45, 90])
      for (let position = 0; position < 9; position++)
        for (const layout of ["single", "repeat"] as const) {
          const plan = planWatermarks(
            { ...defaults, angle, position, layout, size: 25 },
            geometry,
            5,
          );
          geometry.forEach((g, i) => {
            const size = displaySize(g);
            for (const stamp of plan.stamps[i]!) {
              const a = (angle * Math.PI) / 180;
              for (const [x, y] of [
                [-0.5, -0.5],
                [0.5, -0.5],
                [0.5, 0.5],
                [-0.5, 0.5],
              ]) {
                const xx =
                    stamp.cx +
                    x! * stamp.width * Math.cos(a) -
                    y! * stamp.height * Math.sin(a),
                  yy =
                    stamp.cy +
                    x! * stamp.width * Math.sin(a) +
                    y! * stamp.height * Math.cos(a);
                expect(xx).toBeGreaterThanOrEqual(-0.001);
                expect(yy).toBeGreaterThanOrEqual(-0.001);
                expect(xx).toBeLessThanOrEqual(size.width + 0.001);
                expect(yy).toBeLessThanOrEqual(size.height + 0.001);
              }
            }
          });
        }
  });
  it("validates ranges, density, dimensions and Unicode rather than silently clipping or dropping marks", () => {
    const g = geometry.slice(0, 2);
    expect(planWatermarks({ ...defaults, range: "2,2" }, g, 4).pages).toEqual([
      1,
    ]);
    for (const range of ["", "0", "3", "2-1", "oops"])
      expect(() => planWatermarks({ ...defaults, range }, g, 4)).toThrow();
    for (const size of [NaN, 0, 100])
      expect(() => planWatermarks({ ...defaults, size }, g, 4)).toThrow();
    expect(() =>
      planWatermarks(
        { ...defaults, layout: "repeat", angle: 0, size: 10, spacing: "tight" },
        g,
        1000,
      ),
    ).toThrow(/too many/);
    expect(normalizedText("  Cafe\u0301  ")).toBe("Café");
    for (const text of [" ", "a".repeat(121), "x\nY", "x\u200bY", "\u0301"])
      expect(() => normalizedText(text)).toThrow();
    expect(() => textShape(font, "Draft 🙂")).toThrow(/does not support/);
    for (const text of [
      "CONFIDENTIAL",
      "Échantillon reçu",
      "机密文件，仅供审核",
      "社外秘・確認用",
    ]) {
      const shape = textShape(font, text);
      expect(shape.width).toBeGreaterThan(0);
      expect(shape.paths.length).toBeGreaterThan(1);
    }
  });
});
for (const fixture of [
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
]) {
  it(`watermark fixed regression ${fixture} preserves pages and original geometry`, async () => {
    const source = new Uint8Array(await readFile(root + fixture + ".pdf"));
    const settings = {
      ...defaults,
      text:
        fixture === "chinese"
          ? "机密文件"
          : fixture === "japanese"
            ? "社外秘"
            : "CONFIDENTIAL",
    };
    const before = await inspectWatermark(source);
    const result = await watermarkPdf(source, settings, font);
    const after = await inspectWatermark(result);
    expect(after.geometry).toEqual(before.geometry);
    expect(result.length).toBeLessThan(source.length + 200_000);
    if (fixture === "form") {
      const values = (doc: PDFDocument) =>
        doc
          .getForm()
          .getFields()
          .map((f) => ({
            name: f.getName(),
            value: (f as unknown as { getText: () => string }).getText(),
          }));
      expect(values(after.doc)).toEqual(values(before.doc));
    }
    await writeFile(`${folder}/${fixture}-watermarked.pdf`, result);
    await writeFile(
      `${folder}/${fixture}-plan.json`,
      JSON.stringify(
        planWatermarks(
          settings,
          before.geometry,
          textShape(font, settings.text).width /
            textShape(font, settings.text).height,
          before.annotations,
        ),
      ),
    );
  }, 120000);
}
it("handles nonzero CropBox, UserUnit, four rotations, scope, repeated Unicode and image alpha without changing page objects", async () => {
  const doc = await PDFDocument.create(),
    latin = await doc.embedFont(StandardFonts.Helvetica);
  for (const rotation of [0, 90, 180, 270])
    for (const unit of [1, 2]) {
      const page = doc.addPage([500, 700]);
      page.setCropBox(45, 70, 360, 510);
      page.node.set(PDFName.of("UserUnit"), PDFNumber.of(unit));
      page.node.set(PDFName.of("Rotate"), PDFNumber.of(rotation));
      page.drawText(`Original ${rotation}/${unit}`, {
        font: latin,
        x: 60,
        y: 550,
        size: 16,
      });
      page.drawRectangle({
        x: 70,
        y: 100,
        width: 60,
        height: 70,
        color: rgb(0.2, 0.7, 0.3),
      });
    }
  const source = await doc.save(),
    before = await inspectWatermark(source);
  await writeFile(`${folder}/geometry-source.pdf`, source);
  for (const [name, settings] of [
    ["geometry", { ...defaults, text: "机密 SAMPLE", range: "2,4,6,8" }],
    [
      "repeated",
      {
        ...defaults,
        layout: "repeat" as const,
        size: 25,
        text: "REVIEW",
        angle: 0,
        spacing: "wide" as const,
      },
    ],
  ] as const) {
    const result = await watermarkPdf(source, settings, font);
    await writeFile(`${folder}/${name}-watermarked.pdf`, result);
    expect((await inspectWatermark(result)).geometry).toEqual(before.geometry);
    const shape = textShape(font, settings.text);
    await writeFile(
      `${folder}/${name}-plan.json`,
      JSON.stringify(
        planWatermarks(
          settings,
          before.geometry,
          shape.width / shape.height,
          before.annotations,
        ),
      ),
    );
  }
  const imageBytes = new Uint8Array(
    await readFile("docs/ux/public-synthetic-only/image-a.png"),
  );
  const { inspectImage } = await import("../src/photos/model");
  const info = inspectImage(imageBytes),
    image = { bytes: imageBytes, width: info.width, height: info.height };
  const settings = {
    ...defaults,
    type: "image" as const,
    angle: 45,
    position: 8,
    size: 25,
  };
  const result = await watermarkPdf(source, settings, font, image);
  await writeFile(`${folder}/image-watermarked.pdf`, result);
  await writeFile(
    `${folder}/image-plan.json`,
    JSON.stringify(
      planWatermarks(
        settings,
        before.geometry,
        image.width / image.height,
        before.annotations,
      ),
    ),
  );
});
it("preserves forms and links, explains overlap, and rejects forged image dimensions before decoding", async () => {
  const doc = await PDFDocument.load(await readFile(root + "form.pdf"), {
      updateMetadata: false,
    }),
    page = doc.getPage(0);
  page.node
    .Annots()!
    .lookup(0, PDFDict)
    .set(PDFName.of("Rect"), doc.context.obj([220, 375, 380, 425]));
  const link = doc.context.obj({
    Type: "Annot",
    Subtype: "Link",
    Rect: [0, 0, 600, 800],
    A: { S: "URI", URI: PDFString.of("https://example.com") },
  });
  page.node.addAnnot(doc.context.register(link));
  const source = await doc.save({ updateFieldAppearances: false });
  await inspectWatermark(source);
  await expect(
    watermarkPdf(source, { ...defaults, angle: 0 }, font),
  ).rejects.toThrow(/overlaps a form field/);
  const result = await watermarkPdf(
    source,
    { ...defaults, size: 20, position: 6, angle: 0 },
    font,
  );
  const after = await PDFDocument.load(result);
  expect(after.getForm().getTextField("Example0").getText()).toBe("SYNTHETIC");
  expect(after.getPage(0).node.Annots()!.size()).toBe(2);
  const bytes = new Uint8Array(
    await readFile("docs/ux/public-synthetic-only/image-a.png"),
  );
  await expect(
    watermarkPdf(source, { ...defaults, type: "image", position: 6 }, font, {
      bytes,
      width: 1,
      height: 1,
    }),
  ).rejects.toThrow(/dimensions/);
  expect(after.getPage(0).node.Resources()).toBeInstanceOf(PDFDict);
});
for (const file of ["zero-pages.pdf", "corrupted.pdf", "encrypted.pdf"]) {
  it(`refuses edge input ${file}`, async () => {
    const bytes = new Uint8Array(await readFile(root + file));
    await expect(watermarkPdf(bytes, { ...defaults }, font)).rejects.toThrow();
  });
}
