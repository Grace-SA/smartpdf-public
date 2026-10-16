import { test, expect } from "vitest";
import {
  PDFDocument,
  PDFName,
  PDFArray,
  PDFDict,
  PDFString,
  PDFRawStream,
  decodePDFRawStream,
  degrees,
} from "pdf-lib";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { organizePdf, organizeErrors } from "../src/organize/generate";
import { movePages, placePages, type PageEntry } from "../src/organize/model";
import { combinePdfs } from "../src/combine/generate";
const plan = (n: number): PageEntry[] =>
  Array.from({ length: n }, (_, source) => ({
    id: `p${source}`,
    source,
    turns: 0,
  }));
test("optional undefined tag indexes follow the established M2 null normalization", async () => {
  const bytes = new Uint8Array(
    await readFile("tests/fixtures/combine/optional-tag-indexes.pdf"),
  );
  const n = (await PDFDocument.load(bytes)).getPageCount();
  const out = await PDFDocument.load(
    await organizePdf(
      bytes,
      plan(n).map((p) => ({ ...p, turns: 1 })),
    ),
  );
  expect(out.getPage(0).getRotation().angle).toBe(90);
  expect(out.catalog.has(PDFName.of("StructTreeRoot"))).toBe(true);
});

async function document(n = 10) {
  const d = await PDFDocument.create();
  for (let i = 0; i < n; i++) {
    const p = d.addPage([300 + i * 10, 500]);
    p.drawText(`Original page ${i + 1}`);
    if (i === 3) {
      p.setRotation(degrees(90));
      p.setCropBox(10, 20, 250, 400);
    }
  }
  return d;
}
test("ORGANIZE-01 ten pages reorder delete rotate without rebuilding retained contents", async () => {
  const d = await document(),
    original = await d.save(),
    before = Buffer.from(original).toString("hex");
  const entries = plan(10);
  const order = [entries[9]!, ...entries.slice(0, 7)].map((p) =>
    p.source === 3 ? { ...p, turns: 1 } : p,
  );
  const bytes = await organizePdf(original, order),
    out = await PDFDocument.load(bytes);
  expect(out.getPageCount()).toBe(8);
  expect(out.getPages().map((p) => p.getWidth())).toEqual([
    390, 300, 310, 320, 330, 340, 350, 360,
  ]);
  expect(out.getPage(4).getRotation().angle).toBe(180);
  expect(out.getPage(4).getCropBox()).toEqual({
    x: 10,
    y: 20,
    width: 250,
    height: 400,
  });
  expect(Buffer.from(original).toString("hex")).toBe(before);
  for (const [i, e] of order.entries()) {
    const contents = (doc: PDFDocument, index: number) => {
      const a = doc
        .getPage(index)
        .node.lookup(PDFName.of("Contents"), PDFArray);
      return a
        .asArray()
        .map((r) =>
          Buffer.from(
            decodePDFRawStream(doc.context.lookup(r) as PDFRawStream).decode(),
          ).toString("hex"),
        );
    };
    expect(contents(out, i)).toEqual(
      contents(await PDFDocument.load(original), e.source),
    );
  }
  await mkdir("tests/fixtures/organize", { recursive: true });
  await writeFile("tests/fixtures/organize/ten.pdf", original);
  await writeFile("tests/fixtures/organize/eight.pdf", bytes);
  await writeFile(
    "tests/fixtures/organize/hundred.pdf",
    await (await document(100)).save(),
  );
});
test("deleted detached page streams are absent from the serialized object table", async () => {
  const d = await PDFDocument.create();
  for (const text of ["kept-marker", "removed-marker"]) {
    const p = d.addPage();
    p.node.addContentStream(
      d.context.register(d.context.stream(`% ${text}\nq Q`)),
    );
  }
  const out = await PDFDocument.load(
    await organizePdf(await d.save(), plan(1)),
  );
  const streams = out.context
    .enumerateIndirectObjects()
    .filter(([, v]) => v instanceof PDFRawStream)
    .map(([, v]) =>
      new TextDecoder().decode(decodePDFRawStream(v as PDFRawStream).decode()),
    )
    .join("\n");
  expect(streams).toContain("kept-marker");
  expect(streams).not.toContain("removed-marker");
});
test("referenced deleted pages fail; retained navigation survives reordering", async () => {
  const d = await document(2),
    pages = d.getPages();
  const link = d.context.register(
    d.context.obj({
      Type: "Annot",
      Subtype: "Link",
      Rect: [0, 0, 10, 10],
      P: pages[0]!.ref,
      Dest: [pages[1]!.ref, "Fit"],
    }),
  );
  pages[0]!.node.set(PDFName.of("Annots"), d.context.obj([link]));
  const bytes = await d.save();
  await expect(organizePdf(bytes, plan(1))).rejects.toThrow(
    organizeErrors.referenced,
  );
  const out = await PDFDocument.load(
    await organizePdf(bytes, plan(2).reverse()),
  );
  const a = out
    .getPage(1)
    .node.lookup(PDFName.of("Annots"), PDFArray)
    .lookup(0, PDFDict);
  expect(a.lookup(PDFName.of("Dest"), PDFArray).get(0)).toBe(
    out.getPage(0).ref,
  );
  // Removing the page that owns the only link is safe; its target is retained.
  expect(
    (
      await PDFDocument.load(await organizePdf(bytes, [plan(2)[1]!]))
    ).getPageCount(),
  ).toBe(1);
});
test("explicit page labels follow page identity after reordering and deletion", async () => {
  const d = await document(3);
  d.catalog.set(
    PDFName.of("PageLabels"),
    d.context.obj({ Nums: [0, { S: "D", St: 5, P: PDFString.of("A-") }] }),
  );
  const out = await PDFDocument.load(
    await organizePdf(await d.save(), [plan(3)[2]!, plan(3)[0]!]),
  );
  const labels = out.catalog
    .lookup(PDFName.of("PageLabels"), PDFDict)
    .lookup(PDFName.of("Nums"), PDFArray);
  expect(labels.lookup(1, PDFDict).get(PDFName.of("St"))!.toString()).toBe("7");
  expect(labels.lookup(3, PDFDict).get(PDFName.of("St"))!.toString()).toBe("5");
});
test("tagged pages keep structure on reordering; deletion cannot leave dangling tag page references", async () => {
  const bytes = await combinePdfs(
    [
      new Uint8Array(await readFile("tests/fixtures/combine/tag-a.pdf")),
      new Uint8Array(await readFile("tests/fixtures/combine/tag-b.pdf")),
    ],
    () => {},
  );
  const n = (await PDFDocument.load(bytes)).getPageCount();
  const out = await PDFDocument.load(
    await organizePdf(bytes, plan(n).reverse()),
  );
  expect(out.catalog.has(PDFName.of("StructTreeRoot"))).toBe(true);
  await expect(organizePdf(bytes, plan(n).slice(1))).rejects.toThrow(
    organizeErrors.referenced,
  );
});
test("empty duplicate foreign and invalid-rotation plans are rejected", async () => {
  const bytes = await (await document(2)).save();
  for (const entries of [
    [],
    [plan(2)[0]!, plan(2)[0]!],
    [{ id: "bad", source: 4, turns: 0 }],
    [{ id: "bad", source: 0, turns: 1.5 }],
  ])
    await expect(organizePdf(bytes, entries)).rejects.toThrow(
      organizeErrors.invalid,
    );
});
test("deleting content with an unbound tag cannot leave a stale parent index", async () => {
  const d = await PDFDocument.create(),
    p = d.addPage();
  p.node.addContentStream(
    d.context.register(
      d.context.flateStream("/P <</MCID 0>> BDC 0 0 10 10 re f EMC"),
    ),
  );
  p.node.set(PDFName.of("StructParents"), d.context.obj(0));
  d.addPage();
  const root = d.context.obj({ Type: "StructTreeRoot" }),
    ref = d.context.register(root),
    node = d.context.register(
      d.context.obj({ Type: "StructElem", S: "P", P: ref, K: 0 }),
    );
  root.set(PDFName.of("K"), node);
  root.set(PDFName.of("ParentTree"), d.context.obj({ Nums: [0, [node]] }));
  d.catalog.set(PDFName.of("StructTreeRoot"), ref);
  const bytes = await d.save();
  // Unlike the explicit-reference test, no /Pg points at the deleted page.
  // Final structure validation must still reject the orphaned parent index.
  await expect(
    organizePdf(bytes, [{ id: "keep", source: 1, turns: 0 }]),
  ).rejects.toThrow(organizeErrors.output);
});
test("stable identity and multi-selection moves preserve relative order", () => {
  const p = plan(5),
    s = new Set(["p1", "p2"]);
  expect(movePages(p, s, -1).map((p) => p.id)).toEqual([
    "p1",
    "p2",
    "p0",
    "p3",
    "p4",
  ]);
  expect(movePages(p, s, 1).map((p) => p.id)).toEqual([
    "p0",
    "p3",
    "p1",
    "p2",
    "p4",
  ]);
  expect(placePages(p, new Set(["p4"]), 0).map((p) => p.id)).toEqual([
    "p4",
    "p0",
    "p1",
    "p2",
    "p3",
  ]);
  expect(p.map((p) => p.source)).toEqual([0, 1, 2, 3, 4]);
});

test("explicit deletion adjustment preserves visible links and bookmark titles without retargeting", async () => {
  const d = await document(3),
    p = d.getPages();
  const link = d.context.register(
    d.context.obj({
      Type: "Annot",
      Subtype: "Link",
      Rect: [0, 0, 10, 10],
      P: p[1]!.ref,
      Dest: [p[0]!.ref, "Fit"],
    }),
  );
  p[1]!.node.set(PDFName.of("Annots"), d.context.obj([link]));
  const outline = d.context.obj({ Type: "Outlines" }),
    root = d.context.register(outline);
  const b = d.context.register(
    d.context.obj({
      Title: PDFString.of("Original heading"),
      Parent: root,
      Dest: [p[0]!.ref, "Fit"],
    }),
  );
  outline.set(PDFName.of("First"), b);
  outline.set(PDFName.of("Last"), b);
  d.catalog.set(PDFName.of("Outlines"), root);
  d.catalog.set(PDFName.of("OpenAction"), d.context.obj([p[0]!.ref, "Fit"]));
  d.catalog.set(
    PDFName.of("Names"),
    d.context.obj({
      Dests: {
        Names: [
          PDFString.of("gone"),
          [p[0]!.ref, "Fit"],
          PDFString.of("kept"),
          [p[2]!.ref, "Fit"],
        ],
      },
    }),
  );
  const bytes = await d.save(),
    entries = plan(3).slice(1);
  await expect(organizePdf(bytes, entries)).rejects.toThrow(
    organizeErrors.referenced,
  );
  const out = await PDFDocument.load(await organizePdf(bytes, entries, true));
  const savedLink = out
    .getPage(0)
    .node.lookup(PDFName.of("Annots"), PDFArray)
    .lookup(0, PDFDict);
  expect(savedLink.has(PDFName.of("Dest"))).toBe(false);
  const bookmark = out.catalog
    .lookup(PDFName.of("Outlines"), PDFDict)
    .lookup(PDFName.of("First"), PDFDict);
  expect(bookmark.lookup(PDFName.of("Title"), PDFString).decodeText()).toBe(
    "Original heading",
  );
  expect(bookmark.has(PDFName.of("Dest"))).toBe(false);
  expect(out.catalog.has(PDFName.of("OpenAction"))).toBe(false);
  const names = out.catalog
    .lookup(PDFName.of("Names"), PDFDict)
    .lookup(PDFName.of("Dests"), PDFDict)
    .lookup(PDFName.of("Names"), PDFArray);
  expect(names.size()).toBe(2);
  expect(names.lookup(0, PDFString).decodeText()).toBe("kept");
  expect(names.lookup(1, PDFArray).get(0)).toBe(out.getPage(1).ref);
});

test("explicit deletion trims only tags owned by the removed page", async () => {
  const { inspectTags } = await import("../src/combine/tags");
  const bytes = await combinePdfs(
    [
      new Uint8Array(await readFile("tests/fixtures/combine/tag-a.pdf")),
      new Uint8Array(await readFile("tests/fixtures/combine/tag-b.pdf")),
    ],
    () => {},
  );
  const source = await PDFDocument.load(bytes),
    entries = plan(source.getPageCount()).slice(1);
  const out = await PDFDocument.load(await organizePdf(bytes, entries, true));
  const tags = inspectTags(out)!;
  expect(tags).toBeTruthy();
  expect(tags.incomplete).toBe(false);
  expect(out.getPageCount()).toBe(source.getPageCount() - 1);
  for (const node of tags.nodes.values())
    if (node.page !== undefined)
      expect(node.page).toBeLessThan(out.getPageCount());
});
