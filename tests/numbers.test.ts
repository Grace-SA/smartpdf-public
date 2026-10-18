import { describe, it, expect } from "vitest";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import {
  PDFDocument,
  PDFName,
  PDFNumber,
  PDFArray,
  degrees,
  StandardFonts,
} from "pdf-lib";
import {
  defaults,
  numberPages,
  planNumbers,
  type NumberSettings,
} from "../src/numbers/model";
import { glyphShape } from "../src/overlay/text";
import {
  pageGeometry,
  displaySize,
  type Geometry,
} from "../src/overlay/geometry";
import { numberPdf, inspectNumbers } from "../src/numbers/generate";
const font = new Uint8Array(
  await readFile("public/number-fonts/SmartPDFNumberSans-Regular.ttf"),
);
const measure = (text: string) => glyphShape(font, text);
const geometry: Geometry = {
  x: 30,
  y: 50,
  width: 320,
  height: 450,
  rotation: 0,
  unit: 1,
};
const folder = "docs/evidence/m9-output";
await mkdir(folder, { recursive: true });
describe("page numbering rules", () => {
  it("numbers only selected pages, without counting a skipped cover", () => {
    const plan = planNumbers(
      { ...defaults, mode: "skip-first", format: "fraction" },
      Array(6).fill(geometry),
      measure,
    );
    expect(plan.pages).toEqual([1, 2, 3, 4, 5]);
    expect(plan.stamps[0]).toBeNull();
    expect(plan.stamps[1]?.text).toBe("1 / 5");
    expect(plan.stamps[5]?.text).toBe("5 / 5");
  });
  it("uses the same last-number denominator for a custom start and range", () => {
    const plan = planNumbers(
      {
        ...defaults,
        mode: "range",
        from: 2,
        to: 6,
        start: 3,
        format: "page-total",
      },
      Array(6).fill(geometry),
      measure,
    );
    expect(plan.first).toBe(3);
    expect(plan.last).toBe(7);
    expect(plan.stamps[1]?.text).toBe("Page 3 of 7");
    expect(plan.stamps[5]?.text).toBe("Page 7 of 7");
  });
  it("supports a single selected page and all three formats", () => {
    for (const [format, text] of [
      ["number", "12"],
      ["fraction", "12 / 12"],
      ["page-total", "Page 12 of 12"],
    ] as const) {
      const plan = planNumbers(
        { ...defaults, mode: "range", from: 4, to: 4, start: 12, format },
        Array(6).fill(geometry),
        measure,
      );
      expect(plan.stamps[3]?.text).toBe(text);
      expect(plan.pages).toEqual([3]);
    }
  });
  it("rejects empty, reversed, fractional, unsupported and out-of-range settings", () => {
    for (const patch of [
      { start: 0 },
      { start: NaN },
      { start: 999999 },
      { start: 1.5 },
      { format: "unknown" },
      { mode: "unknown" },
      { size: 7 },
      { size: 37 },
      { margin: 2 },
      { margin: 31 },
      { color: "url(x)" },
      { position: 6 },
      { position: 1.5 },
      { mode: "range", from: 0, to: 2 },
      { mode: "range", from: 3, to: 2 },
      { mode: "range", from: 1, to: 7 },
    ])
      expect(() =>
        planNumbers(
          { ...defaults, ...patch } as NumberSettings,
          Array(6).fill(geometry),
          measure,
        ),
      ).toThrow();
    expect(() => numberPages({ ...defaults, mode: "skip-first" }, 1)).toThrow(
      /no pages after/,
    );
    for (const count of [0, 201, NaN])
      expect(() => numberPages(defaults, count)).toThrow();
  });
  it("keeps physical text size and margins in all rotations and user units", () => {
    for (const rotation of [0, 90, 180, 270])
      for (const unit of [1, 2])
        for (let position = 0; position < 6; position++) {
          const g = { ...geometry, rotation, unit },
            stamp = planNumbers({ ...defaults, position }, [g], measure)
              .stamps[0]!,
            size = displaySize(g),
            margin = (defaults.margin * 72) / 25.4;
          expect(stamp.width).toBeCloseTo(
            (measure("1").width * 12) / measure("1").units,
          );
          if (position % 3 === 0) expect(stamp.x).toBeCloseTo(margin);
          if (position % 3 === 1)
            expect(stamp.x + stamp.width / 2).toBeCloseTo(size.width / 2);
          if (position % 3 === 2)
            expect(size.width - stamp.x - stamp.width).toBeCloseTo(margin);
          expect(
            position < 3 ? stamp.y : size.height - stamp.y - stamp.height,
          ).toBeCloseTo(margin);
        }
  });
  it("never clips or silently shrinks numbers and refuses known annotation overlap", () => {
    expect(() =>
      planNumbers(defaults, [{ ...geometry, width: 20, height: 20 }], measure),
    ).toThrow(/too small/);
    const stamp = planNumbers(defaults, [geometry], measure).stamps[0]!;
    expect(() =>
      planNumbers(defaults, [geometry], measure, [
        [{ x: stamp.x, y: stamp.y, width: stamp.width, height: stamp.height }],
      ]),
    ).toThrow(/overlaps/);
    expect(() =>
      planNumbers(defaults, [{ ...geometry, rotation: 45 }], measure),
    ).toThrow(/geometry/);
    expect(() => glyphShape(font, "頁")).toThrow(/does not support/);
  });
});
describe("numbered PDF integration and frozen regressions", () => {
  for (const name of [
    "navigation-a",
    "layer-off",
    "ordinary-tagged-link",
    "final-tags",
  ]) {
    it(`retains existing navigation, layers and tags in ${name}`, async () => {
      const input = new Uint8Array(
        await readFile(`tests/fixtures/combine/${name}.pdf`),
      );
      const original = await PDFDocument.load(input, { updateMetadata: false });
      const output = await numberPdf(input, defaults, font);
      const result = await PDFDocument.load(output, { updateMetadata: false });
      const keys = [
        "Outlines",
        "Names",
        "Dests",
        "OCProperties",
        "StructTreeRoot",
        "MarkInfo",
      ];
      expect(keys.some((key) => original.catalog.has(PDFName.of(key)))).toBe(
        true,
      );
      for (const key of keys) {
        expect(result.catalog.lookup(PDFName.of(key))?.toString()).toBe(
          original.catalog.lookup(PDFName.of(key))?.toString(),
        );
      }
      original.getPages().forEach((page, index) => {
        expect(result.getPage(index).node.Annots()?.toString()).toBe(
          page.node.Annots()?.toString(),
        );
        expect(
          result
            .getPage(index)
            .node.get(PDFName.of("StructParents"))
            ?.toString(),
        ).toBe(page.node.get(PDFName.of("StructParents"))?.toString());
      });
      await writeFile(`${folder}/${name}.pdf`, output);
      await writeFile(
        `${folder}/${name}.json`,
        JSON.stringify({
          source: `tests/fixtures/combine/${name}.pdf`,
          settings: defaults,
          plan: planNumbers(
            defaults,
            original.getPages().map(pageGeometry),
            measure,
          ),
        }),
      );
    });
  }
  for (const name of [
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
    it(`generates and checks ${name}`, async () => {
      const input = new Uint8Array(
        await readFile(`tests/fixtures/m5/${name}.pdf`),
      );
      const source = await PDFDocument.load(input, { updateMetadata: false });
      const output = await numberPdf(
        input,
        { ...defaults, format: "page-total" },
        font,
      );
      const read = await PDFDocument.load(output, { updateMetadata: false });
      expect(read.getPageCount()).toBe(source.getPageCount());
      expect(read.getPages().map(pageGeometry)).toEqual(
        source.getPages().map(pageGeometry),
      );
      await writeFile(`${folder}/${name}.pdf`, output);
      await writeFile(
        `${folder}/${name}.json`,
        JSON.stringify(
          {
            source: `tests/fixtures/m5/${name}.pdf`,
            settings: { ...defaults, format: "page-total" },
            plan: planNumbers(
              { ...defaults, format: "page-total" },
              source.getPages().map(pageGeometry),
              measure,
            ),
          },
          null,
          2,
        ),
      );
    }, 120000);
  }
  for (const name of [
    "zero-pages",
    "corrupted",
    "encrypted",
    "large-50mb",
    "100mb",
  ]) {
    it(`safely refuses ${name}`, async () => {
      const bytes = new Uint8Array(
        await readFile(`tests/fixtures/m5/${name}.pdf`),
      );
      await expect(numberPdf(bytes, defaults, font)).rejects.toThrow();
    }, 120000);
  }
  it("refuses empty input and an oversized font", async () => {
    await expect(numberPdf(new Uint8Array(), defaults, font)).rejects.toThrow();
    await expect(
      numberPdf(
        new Uint8Array(await readFile("tests/fixtures/m5/normal-a4.pdf")),
        defaults,
        new Uint8Array(65537),
      ),
    ).rejects.toThrow(/font/);
  });
  it("preserves PageLabels, interactive forms, all geometry and skipped pages", async () => {
    const source = await PDFDocument.load(
      await readFile("tests/fixtures/m5/form.pdf"),
      { updateMetadata: false },
    );
    source.addPage([300, 400]);
    source.getPage(0).setCropBox(10, 15, 450, 650);
    source.getPage(0).setRotation(degrees(270));
    source.getPage(0).node.set(PDFName.of("UserUnit"), PDFNumber.of(2));
    const labels = source.context.obj({
      Nums: [0, { S: PDFName.of("r") }, 1, { S: PDFName.of("D"), St: 12 }],
    });
    source.catalog.set(
      PDFName.of("PageLabels"),
      source.context.register(labels),
    );
    const bytes = await source.save({ updateFieldAppearances: false }),
      original = await PDFDocument.load(bytes, { updateMetadata: false });
    const output = await numberPdf(
        bytes,
        { ...defaults, mode: "skip-first", format: "fraction" },
        font,
      ),
      result = await PDFDocument.load(output, { updateMetadata: false });
    expect(
      result
        .getForm()
        .getFields()
        .map((f) => f.getName()),
    ).toEqual(
      original
        .getForm()
        .getFields()
        .map((f) => f.getName()),
    );
    expect(result.catalog.lookup(PDFName.of("PageLabels"))!.toString()).toBe(
      original.catalog.lookup(PDFName.of("PageLabels"))!.toString(),
    );
    expect(result.getPages().map(pageGeometry)).toEqual(
      original.getPages().map(pageGeometry),
    );
    expect(
      result.getPage(0).node.lookup(PDFName.of("Contents"), PDFArray).size(),
    ).toBe(
      original.getPage(0).node.lookup(PDFName.of("Contents"), PDFArray).size(),
    );
  });
  it("renders a geometry matrix with numbering only inside the planned regions", async () => {
    const source = await PDFDocument.create(),
      label = await source.embedFont(StandardFonts.Helvetica);
    for (const unit of [1, 2])
      for (const rotation of [0, 90, 180, 270]) {
        const p = source.addPage([390, 550]);
        p.setCropBox(30, 50, 320, 450);
        p.setRotation(degrees(rotation));
        p.node.set(PDFName.of("UserUnit"), PDFNumber.of(unit));
        p.drawText("SYNTHETIC GEOMETRY", {
          x: 70,
          y: 300,
          size: 12,
          font: label,
        });
      }
    const input = await source.save({ updateFieldAppearances: false });
    await writeFile(`${folder}/geometry-source.pdf`, input);
    for (let position = 0; position < 6; position++) {
      const settings = {
        ...defaults,
        position,
        mode: "range" as const,
        from: 2,
        to: 7,
        start: 3,
        format: "fraction" as const,
      };
      const output = await numberPdf(input, settings, font),
        { geometry: gs } = await inspectNumbers(input);
      await writeFile(`${folder}/geometry-${position}.pdf`, output);
      await writeFile(
        `${folder}/geometry-${position}.json`,
        JSON.stringify(
          {
            source: `${folder}/geometry-source.pdf`,
            settings,
            plan: planNumbers(settings, gs, measure),
          },
          null,
          2,
        ),
      );
    }
  });
});
