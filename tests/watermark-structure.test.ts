import { test, expect } from "vitest";
import { readFile, writeFile } from "node:fs/promises";
import { PDFDocument } from "pdf-lib";
import { inspectWatermark, watermarkPdf } from "../src/watermark/generate";
import { defaults, planWatermarks } from "../src/watermark/model";
import { textShape } from "../src/watermark/font";

const font = new Uint8Array(
  await readFile("public/watermark-fonts/SmartPDFSans-Regular.ttf"),
);
for (const name of [
  "final-color",
  "navigation-a",
  "tag-a",
  "layer-on",
  "layer-off",
  "ordinary-comments",
  "final-form",
  "ordinary-tagged-link",
  "optional-tag-indexes",
]) {
  test(`watermark retains supported document structure: ${name}`, async () => {
    const source = new Uint8Array(
      await readFile(`tests/fixtures/combine/${name}.pdf`),
    );
    const before = await inspectWatermark(source);
    const settings = {
      ...defaults,
      text: "REVIEW",
      size: 10,
      angle: 0,
      position: 8,
    };
    const shape = textShape(font, settings.text);
    const plan = planWatermarks(
      settings,
      before.geometry,
      shape.width / shape.height,
      before.annotations,
    );
    const result = await watermarkPdf(source, settings, font);
    const after = await PDFDocument.load(result, { updateMetadata: false });
    expect(after.catalog.toString()).toBe(before.doc.catalog.toString());
    expect(after.getPages().map((p) => p.ref.toString())).toEqual(
      before.doc.getPages().map((p) => p.ref.toString()),
    );
    after.getPages().forEach((page, index) => {
      expect(page.node.Annots()?.toString()).toBe(
        before.doc.getPage(index).node.Annots()?.toString(),
      );
      expect(page.getMediaBox()).toEqual(
        before.doc.getPage(index).getMediaBox(),
      );
    });
    await writeFile(
      `docs/evidence/m10-output/structure-${name}-watermarked.pdf`,
      result,
    );
    await writeFile(
      `docs/evidence/m10-output/structure-${name}-plan.json`,
      JSON.stringify(plan),
    );
  });
}
