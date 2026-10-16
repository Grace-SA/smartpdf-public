import { test, expect } from "vitest";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import {
  PDFDocument,
  PDFName,
  PDFNumber,
  PDFDict,
  PDFString,
  degrees,
} from "pdf-lib";
import { inspectPdf } from "../src/combine/generate";
import { probePdf } from "../src/core/probe";
import { signPdf, inspectSign } from "../src/sign/generate";
import {
  imageTransform,
  displaySize,
  fits,
  constrain,
  type Geometry,
  type Placement,
} from "../src/sign/model";
const read = async (name: string) =>
  new Uint8Array(await readFile("tests/fixtures/m5/" + name));
const p: Placement = {
  id: "s1",
  asset: "a",
  page: 0,
  x: 30,
  y: 40,
  width: 120,
  height: 40,
};
test("existing certificate signature is reported before unsupported form fields", async () => {
  const doc = await PDFDocument.create();
  doc.addPage();
  const signature = doc.context.register(
    doc.context.obj({
      Type: "Sig",
      ByteRange: [0, 10, 20, 30],
      Contents: PDFString.of("synthetic"),
    }),
  );
  const field = doc.context.register(
    doc.context.obj({ FT: "Sig", V: signature }),
  );
  doc.catalog.set(
    PDFName.of("AcroForm"),
    doc.context.obj({ Fields: [field], SigFlags: 3 }),
  );
  const result = await probePdf(await doc.save(), "preview");
  expect(!result.ok && result.reason).toBe("signature");
});
test("SIGN preserves passive stamp extensions in place without weakening copy checks", async () => {
  const doc = await PDFDocument.load(await read("normal-a4.pdf"));
  const page = doc.getPage(0);
  const stamp = doc.context.obj({
    Type: "Annot",
    Subtype: "Stamp",
    Rect: [200, 200, 300, 250],
    P: page.ref,
    Page: page.ref,
    TrnCustomData: PDFString.of('{"custom":"preserved"}'),
  });
  page.node.set(
    PDFName.of("Annots"),
    doc.context.obj([doc.context.register(stamp)]),
  );
  const source = await doc.save();
  expect((await inspectPdf(source)).ok).toBe(false);
  await expect(inspectSign(source)).resolves.toBeDefined();
  const result = await signPdf(
    source,
    [{ id: "a", bytes: await read("signature.png") }],
    [p],
  );
  const saved = await PDFDocument.load(result),
    savedPage = saved.getPage(0);
  const savedStamp = savedPage.node.Annots()!.lookup(0, PDFDict);
  expect(
    savedStamp.lookup(PDFName.of("TrnCustomData"), PDFString).decodeText(),
  ).toBe('{"custom":"preserved"}');
  expect(saved.context.lookup(savedStamp.get(PDFName.of("Page")))).toBe(
    savedPage.node,
  );
  expect((await inspectPdf(result)).ok).toBe(false);
  stamp.set(
    PDFName.of("TrnCustomData"),
    doc.context.obj({ JS: PDFString.of("app.alert('test')") }),
  );
  await expect(inspectSign(await doc.save())).rejects.toThrow();
});
for (const angle of [0, 90, 180, 270])
  test(`SIGN-01 rotated ${angle} CropBox and UserUnit mapping`, async () => {
    const g: Geometry = {
      x: 17,
      y: 29,
      width: 400,
      height: 600,
      rotation: angle,
      unit: 2,
    };
    const t = imageTransform(p, g),
      a = (angle * Math.PI) / 180;
    const pdfCorners = [
      [t.x, t.y],
      [t.x + t.width * Math.cos(a), t.y + t.width * Math.sin(a)],
      [t.x - t.height * Math.sin(a), t.y + t.height * Math.cos(a)],
    ];
    function screen([x, y]: number[]) {
      const u = (x! - g.x) * 2,
        v = (y! - g.y) * 2;
      return angle === 0
        ? [u, 1200 - v]
        : angle === 90
          ? [v, u]
          : angle === 180
            ? [800 - u, v]
            : [1200 - v, 800 - u];
    }
    const expected = [
      [30, 80],
      [150, 80],
      [30, 40],
    ];
    pdfCorners
      .map(screen)
      .forEach((xy, i) =>
        xy.forEach((v, j) => expect(v).toBeCloseTo(expected[i]![j]!, 8)),
      );
    const doc = await PDFDocument.create(),
      page = doc.addPage([450, 680]);
    page.setCropBox(17, 29, 400, 600);
    page.setRotation(degrees(angle));
    page.node.set(PDFName.of("UserUnit"), PDFNumber.of(2));
    page.drawText("Original text");
    const input = await doc.save();
    const result = await signPdf(
      input,
      [{ id: "a", bytes: await read("signature.png") }],
      [p],
    );
    await mkdir("docs/evidence/m5-output", { recursive: true });
    await writeFile(
      `docs/evidence/m5-output/geometry-${angle}-source.pdf`,
      input,
    );
    await writeFile(`docs/evidence/m5-output/geometry-${angle}.pdf`, result);
    const out = await PDFDocument.load(result);
    expect(out.getPage(0).getCropBox()).toEqual({
      x: 17,
      y: 29,
      width: 400,
      height: 600,
    });
  });
test("invalid and boundary placements cannot generate output", async () => {
  const bytes = await read("normal-a4.pdf"),
    assets = [{ id: "a", bytes: await read("signature.png") }];
  for (const bad of [
    { ...p, x: NaN },
    { ...p, width: 0 },
    { ...p, x: -1 },
    { ...p, page: 200 },
    { ...p, asset: "missing" },
    { ...p, width: 9999 },
  ])
    await expect(signPdf(bytes, assets, [bad])).rejects.toThrow();
  await expect(signPdf(bytes, assets, [])).rejects.toThrow();
  const g: Geometry = {
    x: 0,
    y: 0,
    width: 100,
    height: 80,
    rotation: 0,
    unit: 1,
  };
  expect(fits(constrain({ ...p, x: 200, width: 200, height: 60 }, g), g)).toBe(
    true,
  );
  expect(displaySize(g)).toEqual({ width: 100, height: 80 });
});
test("malformed oversized signature image refused before decoding", async () => {
  const bytes = await read("normal-a4.pdf"),
    image = await read("signature.png");
  new DataView(image.buffer).setUint32(16, 100000);
  await expect(
    signPdf(bytes, [{ id: "a", bytes: image }], [p]),
  ).rejects.toThrow("pixel budget");
});
test("inspection does not mutate its source", async () => {
  const b = await read("normal-a4.pdf"),
    copy = b.slice();
  await inspectSign(b);
  expect(b).toEqual(copy);
});

test("signature overlapping a form widget is refused instead of hidden in the export", async () => {
  const bytes = await read("form.pdf"),
    copy = bytes.slice();
  await expect(
    signPdf(
      bytes,
      [{ id: "a", bytes: await read("signature.png") }],
      [{ ...p, x: 40, y: 100 }],
    ),
  ).rejects.toThrow("overlaps a form field or annotation");
  expect(bytes).toEqual(copy);
});

test("signature count and asset budgets are enforced at the worker boundary", async () => {
  const bytes = await read("normal-a4.pdf"),
    image = await read("signature.png");
  const assets = [{ id: "a", bytes: image }];
  await expect(
    signPdf(
      bytes,
      assets,
      Array.from({ length: 101 }, (_, i) => ({ ...p, id: String(i) })),
    ),
  ).rejects.toThrow("Invalid signature draft");
  await expect(
    signPdf(
      bytes,
      Array.from({ length: 21 }, (_, i) => ({ id: String(i), bytes: image })),
      [p],
    ),
  ).rejects.toThrow("Invalid signature draft");
  await expect(signPdf(bytes, assets, [p, { ...p }])).rejects.toThrow(
    "Invalid signature draft",
  );
  const output = await signPdf(
    bytes,
    assets,
    Array.from({ length: 100 }, (_, i) => ({ ...p, id: String(i) })),
  );
  expect((await PDFDocument.load(output)).getPageCount()).toBe(2);
});
