import { test, expect } from "vitest";
import {
  PDFDocument,
  PDFName,
  PDFString,
  PDFDict,
  PDFArray,
  PDFNumber,
  PDFRawStream,
} from "pdf-lib";
import { deflateSync } from "node:zlib";
import { combinePdfs, inspectPdf } from "../src/combine/generate";
import { inspectTags } from "../src/combine/tags";
import { probePdf } from "../src/core/probe";
import { LIMITS } from "../src/core/contracts";
import { writeFile, readFile } from "node:fs/promises";
const k = PDFName.of;

async function taggedLink() {
  const d = await PDFDocument.create(),
    p = d.addPage();
  p.drawText("A tagged link");
  const root = d.context.obj({ Type: "StructTreeRoot" }),
    rr = d.context.register(root);
  const link = d.context.obj({
    Type: "Annot",
    Subtype: "Link",
    Rect: [10, 10, 100, 30],
    P: p.ref,
    StructParent: 0,
    A: { S: "URI", URI: PDFString.of("https://example.com") },
  });
  const lr = d.context.register(link);
  const node = d.context.obj({
    Type: "StructElem",
    S: "Link",
    P: rr,
    Pg: p.ref,
    ID: PDFString.of("same-id"),
    K: { Type: "OBJR", Obj: lr, Pg: p.ref },
  });
  const nr = d.context.register(node);
  root.set(k("K"), nr);
  root.set(
    k("ParentTree"),
    d.context.obj({ Type: "ParentTree", Nums: [0, nr] }),
  );
  root.set(
    k("IDTree"),
    d.context.obj({ Names: [PDFString.of("same-id"), nr] }),
  );
  p.node.set(k("Annots"), d.context.obj([lr]));
  d.catalog.set(k("StructTreeRoot"), rr);
  d.catalog.set(
    k("MarkInfo"),
    d.context.obj({ Type: "MarkInfo", Marked: true }),
  );
  return { d, link, node, root };
}
test("tagged links and colliding structure IDs survive repeated inputs and another combine", async () => {
  const { d } = await taggedLink(),
    bytes = await d.save();
  await writeFile("tests/fixtures/combine/ordinary-tagged-link.pdf", bytes);
  const merged = await combinePdfs([bytes, bytes], () => {});
  const out = await PDFDocument.load(merged),
    plan = inspectTags(out)!;
  expect(plan.objectUses.size).toBe(2);
  expect(plan.ids.size).toBe(2);
  for (const [annotation, use] of plan.objectUses) {
    expect(annotation.get(k("P"))).toBe(out.getPage(use.page).ref);
    expect(annotation.lookup(k("StructParent"), PDFNumber).asNumber()).toBe(
      use.page,
    );
  }
  expect(
    (await inspectPdf(await combinePdfs([merged, bytes], () => {}))).ok,
  ).toBe(true);
});
test("broken annotation tag mappings and ID trees remain blocked", async () => {
  for (const kind of ["index", "id", "object"]) {
    const { d, link, node, root } = await taggedLink();
    if (kind === "index") link.set(k("StructParent"), PDFNumber.of(4));
    if (kind === "id")
      root.set(
        k("IDTree"),
        d.context.obj({
          Names: [PDFString.of("different"), d.context.register(node)],
        }),
      );
    if (kind === "object")
      node.set(k("K"), d.context.obj({ Type: "OBJR", Obj: d.getPage(0).ref }));
    expect((await inspectPdf(await d.save())).ok).toBe(false);
  }
});
test("passive annotations preserve popup, reply, page and appearance identity", async () => {
  const d = await PDFDocument.create(),
    p = d.addPage();
  const note = d.context.obj({
    Type: "Annot",
    Subtype: "Text",
    Rect: [10, 10, 30, 30],
    Contents: PDFString.of("Keep comment"),
    P: p.ref,
  });
  const nr = d.context.register(note);
  const popup = d.context.obj({
    Type: "Annot",
    Subtype: "Popup",
    Rect: [30, 30, 130, 130],
    Parent: nr,
    Open: false,
  });
  const pr = d.context.register(popup);
  note.set(k("Popup"), pr);
  const reply = d.context.obj({
    Type: "Annot",
    Subtype: "Text",
    Rect: [10, 40, 30, 60],
    IRT: nr,
    RT: "R",
    Contents: PDFString.of("Reply"),
  });
  p.node.set(k("Annots"), d.context.obj([nr, pr, d.context.register(reply)]));
  const bytes = await d.save();
  await writeFile("tests/fixtures/combine/ordinary-comments.pdf", bytes);
  expect((await probePdf(bytes, "preview")).ok).toBe(true);
  expect((await probePdf(bytes)).ok).toBe(false);
  const out = await PDFDocument.load(
    await combinePdfs([bytes, bytes], () => {}),
  );
  for (const p of out.getPages()) {
    const a = p.node.lookup(k("Annots"), PDFArray);
    expect(a.lookup(0, PDFDict).get(k("Popup"))).toBe(a.get(1));
    expect(a.lookup(1, PDFDict).get(k("Parent"))).toBe(a.get(0));
    expect(a.lookup(2, PDFDict).get(k("IRT"))).toBe(a.get(0));
    expect(a.lookup(0, PDFDict).get(k("P"))).toBe(p.ref);
    expect(
      a.lookup(0, PDFDict).lookup(k("Contents"), PDFString).decodeText(),
    ).toBe("Keep comment");
  }
  note.set(
    k("AA"),
    d.context.obj({ E: { S: "JavaScript", JS: PDFString.of("app.alert(1)") } }),
  );
  expect((await inspectPdf(await d.save())).ok).toBe(false);
});
test("ordinary RGB scans use a bounded image decoder without raising content-stream limits", async () => {
  const d = await PDFDocument.create(),
    p = d.addPage([300, 300]);
  const image = d.context.register(
    d.context.stream(deflateSync(Buffer.alloc(3072 * 3072 * 3, 240)), {
      Type: "XObject",
      Subtype: "Image",
      Width: 3072,
      Height: 3072,
      BitsPerComponent: 8,
      ColorSpace: "DeviceRGB",
      Filter: "FlateDecode",
    }),
  );
  p.node.set(k("Resources"), d.context.obj({ XObject: { Scan: image } }));
  p.node.addContentStream(
    d.context.register(d.context.stream("q 300 0 0 300 0 0 cm /Scan Do Q")),
  );
  const bytes = await d.save();
  expect((await probePdf(bytes, "preview")).ok).toBe(true);
  expect(
    (await inspectPdf(await combinePdfs([bytes, bytes], () => {}))).ok,
  ).toBe(true);
  await writeFile("tests/fixtures/combine/ordinary-scan.pdf", bytes);
  d.context.assign(
    image,
    d.context.stream(deflateSync(Buffer.alloc(LIMITS.decodedImageBytes + 1)), {
      Type: "XObject",
      Subtype: "Image",
      Width: 3072,
      Height: 3072,
      BitsPerComponent: 8,
      ColorSpace: "DeviceRGB",
      Filter: "FlateDecode",
    }),
  );
  expect(await probePdf(await d.save(), "preview")).toMatchObject({
    ok: false,
    code: "RESOURCE_LIMIT",
  });
});
test("losslessly wrapped native image filters no longer look like damaged PDFs", async () => {
  const d = await PDFDocument.create(),
    p = d.addPage();
  const image = await d.embedJpg(
    await readFile("tests/fixtures/photos/red.jpg"),
  );
  p.drawImage(image, { x: 10, y: 10, width: 100, height: 100 });
  await image.embed();
  const stream = d.context.lookup(image.ref);
  if (!(stream instanceof PDFRawStream))
    throw Error("Expected embedded JPEG stream");
  const dict = stream.dict.clone();
  dict.set(k("Filter"), d.context.obj(["FlateDecode", "DCTDecode"]));
  d.context.assign(
    image.ref,
    PDFRawStream.of(dict, deflateSync(stream.contents)),
  );
  const bytes = await d.save();
  expect((await probePdf(bytes, "preview")).ok).toBe(true);
  expect(
    (await inspectPdf(await combinePdfs([bytes, bytes], () => {}))).ok,
  ).toBe(true);
  await writeFile("tests/fixtures/combine/ordinary-wrapped-image.pdf", bytes);
});
