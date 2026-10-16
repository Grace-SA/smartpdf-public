import { test, expect } from "vitest";
import {
  PDFDocument,
  PDFDict,
  PDFName,
  PDFString,
  PDFArray,
  PDFBool,
  PDFRef,
  PDFNull,
} from "pdf-lib";
import { writeFile } from "node:fs/promises";
import { combinePdfs, inspectPdf } from "../src/combine/generate";
import { inspectTags } from "../src/combine/tags";
import { inspectNavigation } from "../src/combine/navigation";
const k = PDFName.of;
test("bookmark structure targets point to the copied logical node rather than a detached duplicate", async () => {
  const d = await fixture("P", "en-US"),
    tag = d.catalog.lookup(k("StructTreeRoot"), PDFDict).get(k("K"))!,
    outline = d.context.obj({ Type: "Outlines" }),
    ref = d.context.register(outline);
  const item = d.context.register(
    d.context.obj({
      Title: PDFString.of("Section"),
      Parent: ref,
      Dest: [d.getPage(0).ref, "Fit"],
      SE: tag,
    }),
  );
  outline.set(k("First"), item);
  outline.set(k("Last"), item);
  d.catalog.set(k("Outlines"), ref);
  const bytes = await d.save(),
    out = await PDFDocument.load(await combinePdfs([bytes, bytes], () => {})),
    tags = inspectTags(out)!;
  for (const bookmark of inspectNavigation(out).bookmarks) {
    const node = out.context.lookup(bookmark.source.get(k("SE")), PDFDict);
    expect(tags.nodes.has(node)).toBe(true);
  }
});
test("namespace identity, P-only ancestors and inconsistent ParentTree ownership are retained", async () => {
  const d = await fixture("P", "en-US"),
    root = d.catalog.lookup(k("StructTreeRoot"), PDFDict),
    node = d.context.lookup(root.get(k("K")), PDFDict);
  const ns = d.context.register(
    d.context.obj({
      Type: "Namespace",
      NS: PDFString.of("http://iso.org/pdf/ssn"),
    }),
  );
  root.set(k("Namespaces"), d.context.obj([ns]));
  node.set(k("NS"), ns);
  node.set(k("S"), k("P"));
  const ancestor = d.context.register(
    d.context.obj({
      Type: "StructElem",
      S: "Sect",
      P: d.catalog.get(k("StructTreeRoot")),
      Pg: d.getPage(0).ref,
    }),
  );
  node.set(k("P"), ancestor);
  root.set(k("ParentTree"), d.context.obj({ Nums: [0, [ancestor]] }));
  const bytes = await d.save();
  await writeFile("tests/fixtures/combine/final-tags.pdf", bytes);
  const out = await PDFDocument.load(
      await combinePdfs([bytes, bytes], () => {}),
    ),
    plan = inspectTags(out)!;
  expect(plan.namespaces).toHaveLength(2);
  expect(plan.parents).toHaveLength(2);
  for (const wrapper of plan.children) {
    const child = wrapper.kids[0]!;
    expect("source" in child).toBe(true);
    if (!("source" in child) || !child.source) throw Error("Missing child");
    const p = out.context.lookup(child.source.get(k("P")), PDFDict);
    expect(p.lookup(k("S"), PDFName)).toBe(k("Sect"));
    expect(child.source.lookup(k("S"), PDFName)).toBe(k("P"));
    expect(plan.parents.some((entry) => entry.entries.includes(p))).toBe(true);
  }
  expect(out.catalog.lookup(k("MarkInfo"), PDFDict).get(k("Suspects"))).toBe(
    PDFBool.True,
  );
});
test("orphan page indexes remain orphaned and cannot bind to another input's tag tree", async () => {
  const plain = await PDFDocument.create();
  plain.addPage().drawText("/MCID 0 is just text");
  plain.getPage(0).node.set(k("StructParents"), plain.context.obj(0));
  const bytes = await plain.save(),
    tagged = await (await fixture("P", "en-US")).save();
  const out = await PDFDocument.load(
      await combinePdfs([bytes, tagged, bytes], () => {}),
    ),
    plan = inspectTags(out)!;
  expect(plan.parents.map((v) => v.page)).toEqual([1]);
  const indices = out
    .getPages()
    .map((p) => p.node.get(k("StructParents"))!.toString());
  expect(new Set(indices).size).toBe(3);
});
test("numeric MCIDs without explicit page are not rewritten into invented page bindings", async () => {
  const d = await fixture("P", "en-US"),
    root = d.catalog.lookup(k("StructTreeRoot"), PDFDict),
    node = d.context.lookup(root.get(k("K")), PDFDict);
  node.delete(k("Pg"));
  const bytes = await d.save(),
    out = await PDFDocument.load(await combinePdfs([bytes, bytes], () => {})),
    plan = inspectTags(out)!;
  for (const wrapper of plan.children) {
    const child = wrapper.kids[0]!;
    if (!("source" in child) || !child.source) throw Error("Missing child");
    expect(child.source.has(k("Pg"))).toBe(false);
    expect(child.source.get(k("K"))!.toString()).toBe("0");
  }
});
async function fixture(role: string, language: string) {
  const d = await PDFDocument.create(),
    p = d.addPage([300, 300]);
  p.drawText("Tagged content", { x: 30, y: 200 });
  // Enclose the generated content in one marked-content sequence.
  const streams = p.node.Contents() as PDFArray;
  p.node.set(
    k("Contents"),
    d.context.obj([
      d.context.register(d.context.flateStream("/P <</MCID 0>> BDC")),
      ...streams.asArray(),
      d.context.register(d.context.flateStream("EMC")),
    ]),
  );
  p.node.set(k("StructParents"), d.context.obj(0));
  const root = d.context.obj({ Type: "StructTreeRoot" }),
    ref = d.context.register(root);
  const node = d.context.obj({
    Type: "StructElem",
    S: "Custom",
    P: ref,
    Pg: p.ref,
    K: 0,
    C: "Shared",
    Alt: PDFString.of("Description"),
    ActualText: PDFString.of("Accessible content"),
  });
  const nref = d.context.register(node);
  root.set(k("K"), nref);
  root.set(k("ParentTree"), d.context.obj({ Nums: [0, [nref]] }));
  root.set(k("ParentTreeNextKey"), d.context.obj(1));
  root.set(k("RoleMap"), d.context.obj({ Custom: role }));
  root.set(
    k("ClassMap"),
    d.context.obj({
      Shared: { O: "Layout", SpaceBefore: role === "P" ? 12 : 24 },
    }),
  );
  d.catalog.set(k("StructTreeRoot"), ref);
  d.catalog.set(k("MarkInfo"), d.context.obj({ Marked: true }));
  d.catalog.set(k("Lang"), PDFString.of(language));
  return d;
}
test("tags preserve semantic roles, class collisions, language and MCID mappings for repeated inputs", async () => {
  const a = await (await fixture("P", "en-US")).save(),
    b = await (await fixture("H1", "zh-CN")).save();
  const bytes = await combinePdfs([b, a, b], () => {}),
    d = await PDFDocument.load(bytes),
    plan = inspectTags(d)!;
  expect(plan.parents.map((p) => p.page)).toEqual([0, 1, 2]);
  expect(plan.children.length).toBe(3);
  expect(plan.nodes.size).toBe(6);
  expect(plan.roles!.keys().length).toBe(3);
  expect(plan.classes!.keys().length).toBe(3);
  expect(
    plan.children.map((n) =>
      n.source.lookup(k("Lang"), PDFString).decodeText(),
    ),
  ).toEqual(["zh-CN", "en-US", "zh-CN"]);
  expect(d.catalog.lookup(k("MarkInfo"), PDFDict).get(k("Suspects"))).toBe(
    PDFBool.False,
  );
  await writeFile("tests/fixtures/combine/tag-a.pdf", a);
  await writeFile("tests/fixtures/combine/tag-b.pdf", b);
  await writeFile("docs/private-samples/m2/tags.pdf", bytes);
  const plain = await PDFDocument.create();
  plain.addPage();
  const mixed = await PDFDocument.load(
    await combinePdfs([a, await plain.save()], () => {}),
  );
  expect(mixed.catalog.lookup(k("MarkInfo"), PDFDict).get(k("Suspects"))).toBe(
    PDFBool.True,
  );
  expect(inspectTags(mixed)!.parents.length).toBe(1);
});
test("tag mapping corruption and unsupported object references cannot produce a result", async () => {
  for (const kind of ["parent", "mcid", "role", "object", "id"]) {
    const d = await fixture("P", "en-US"),
      root = d.catalog.lookup(k("StructTreeRoot"), PDFDict),
      node = d.context.lookup(root.get(k("K")), PDFDict);
    if (kind === "parent") node.set(k("P"), d.getPage(0).ref);
    if (kind === "mcid") node.set(k("K"), d.context.obj(-1));
    if (kind === "role")
      root.set(k("RoleMap"), d.context.obj({ Custom: "Custom" }));
    if (kind === "object")
      node.set(k("K"), d.context.obj({ Type: "OBJR", Obj: d.getPage(0).ref }));
    if (kind === "id") node.set(k("ID"), PDFString.of("unique"));
    const result = await inspectPdf(await d.save());
    expect(result.ok, kind).toBe(false);
    if (!result.ok) expect(result.reason).toBe("tagged");
  }
});

test("unmapped custom roles are preserved without inventing semantics, including repeat merges", async () => {
  const d = await fixture("P", "en-US");
  const root = d.catalog.lookup(k("StructTreeRoot"), PDFDict);
  const node = d.context.lookup(root.get(k("K")), PDFDict);
  node.set(k("S"), k("Strong"));
  root.delete(k("RoleMap"));
  const source = await d.save();
  await writeFile("tests/fixtures/combine/custom-role.pdf", source);
  const mapped = await fixture("P", "en-US");
  mapped.catalog
    .lookup(k("StructTreeRoot"), PDFDict)
    .set(k("RoleMap"), mapped.context.obj({ Custom: "Strong", Strong: "P" }));
  const output = await combinePdfs(
    [source, await mapped.save(), source],
    () => {},
  );
  const out = await PDFDocument.load(output),
    plan = inspectTags(out)!;
  expect(plan.unmappedRoles.has("Strong")).toBe(true);
  expect(
    [...plan.nodes.keys()].filter((n) => n.get(k("S")) === k("Strong")),
  ).toHaveLength(2);
  expect(plan.mark.get(k("Suspects"))).toBe(PDFBool.True);
  expect(plan.roles?.has(k("Strong"))).toBe(false);
  expect(
    (await inspectPdf(await combinePdfs([output, source], () => {}))).ok,
  ).toBe(true);
  const bad = await fixture("P", "en-US");
  const br = bad.catalog.lookup(k("StructTreeRoot"), PDFDict);
  bad.context
    .lookup(br.get(k("K")), PDFDict)
    .set(k("S"), PDFString.of("Strong"));
  expect((await inspectPdf(await bad.save())).ok).toBe(false);
});

test("unmapped roles cannot acquire another input's generated mapping", async () => {
  const a = await fixture("P", "en-US"),
    b = await fixture("P", "en-US");
  const root = b.catalog.lookup(k("StructTreeRoot"), PDFDict);
  b.context
    .lookup(root.get(k("K")), PDFDict)
    .set(k("S"), k("document-1:Custom"));
  root.delete(k("RoleMap"));
  await expect(
    combinePdfs([await a.save(), await b.save()], () => {}),
  ).rejects.toThrow("Custom tag names conflict");
});

async function indexedLeaf() {
  const d = await fixture("P", "en-US"),
    p = d.getPage(0);
  const root = d.catalog.lookup(k("StructTreeRoot"), PDFDict);
  const parent = d.context.lookup(root.get(k("K")), PDFDict);
  const detached = d.context.obj({
    Type: "StructElem",
    S: "Artifact",
    P: root.get(k("K")),
    Pg: p.ref,
    K: 1,
    Alt: PDFString.of("Decoration metadata"),
  });
  const ref = d.context.register(detached);
  root.set(
    k("ParentTree"),
    d.context.obj({ Nums: [0, [root.get(k("K")), ref]] }),
  );
  p.node.addContentStream(
    d.context.register(
      d.context.flateStream(
        "/Artifact <</MCID 1>> BDC\n0.8 g 10 10 25 25 re f\nEMC",
      ),
    ),
  );
  return { d, p, root, parent, detached };
}
test("content-indexed leaves outside reading order retain both graphs across repeated merges", async () => {
  const { d } = await indexedLeaf();
  const bytes = await d.save();
  await writeFile("tests/fixtures/combine/indexed-artifact.pdf", bytes);
  const original = inspectTags(d)!;
  expect(original.detached).toHaveLength(1);
  expect(original.children[0]!.kids).toHaveLength(1);
  const out = await PDFDocument.load(
    await combinePdfs([bytes, bytes], () => {}),
  );
  const plan = inspectTags(out)!;
  expect(plan.detached).toHaveLength(2);
  expect(plan.mark.get(k("Suspects"))).toBe(PDFBool.True);
  for (const entry of plan.detached) {
    expect(entry.node.source.lookup(k("Alt"), PDFString).decodeText()).toBe(
      "Decoration metadata",
    );
    expect(entry.parent).not.toBe(entry.node.source);
    expect(plan.parents[entry.node.page!]!.entries[1]).toBe(entry.node.source);
  }
  expect(plan.children).toHaveLength(2);
  expect(
    (await inspectPdf(await combinePdfs([await out.save(), bytes], () => {})))
      .ok,
  ).toBe(true);
});
test("detached tags reject invalid parents, absent pages, negative identifiers and cycles", async () => {
  for (const kind of ["parent", "page", "mcid", "subtree"]) {
    const { d, detached, parent } = await indexedLeaf();
    if (kind === "parent") detached.set(k("P"), d.getPage(0).ref);
    if (kind === "page") detached.set(k("Pg"), PDFRef.of(99999));
    if (kind === "mcid") detached.set(k("K"), d.context.obj(-2));
    if (kind === "collision") parent.set(k("K"), d.context.obj([0, 1]));
    if (kind === "subtree") detached.set(k("K"), d.context.register(detached));
    expect((await inspectPdf(await d.save())).ok, kind).toBe(false);
  }
});

test("optional absent indexes preserve unindexed tags, null leaves and original parent links", async () => {
  const d = await fixture("P", "en-US");
  const root = d.catalog.lookup(k("StructTreeRoot"), PDFDict);
  const parent = d.context.lookup(root.get(k("K")), PDFDict);
  const leaf = d.context.obj({ S: "Span", P: root.get(k("K")), K: PDFNull });
  parent.set(k("K"), d.context.obj([0, d.context.register(leaf)]));
  d.getPage(0).node.delete(k("StructParents"));
  root.set(k("ParentTree"), PDFRef.of(99991));
  root.set(k("IDTree"), PDFRef.of(99992));
  d.catalog.delete(k("MarkInfo"));
  parent.delete(k("P"));
  const bytes = await d.save();
  await writeFile("tests/fixtures/combine/optional-tag-indexes.pdf", bytes);
  expect((await inspectPdf(bytes)).ok).toBe(true);
  const out = await PDFDocument.load(
    await combinePdfs([bytes, bytes], () => {}),
  );
  const plan = inspectTags(out)!;
  expect(plan.parents).toHaveLength(0);
  expect(plan.mark.get(k("Suspects"))).toBe(PDFBool.True);
  for (const wrapper of plan.children) {
    const original = wrapper.kids[0]!;
    expect("kids" in original).toBe(true);
    if (!("kids" in original)) throw Error("missing source tree");
    expect(original.source.has(k("P"))).toBe(false);
    const child = original.kids[1]!;
    if (!("kids" in child)) throw Error("missing leaf");
    expect(plan.sourceParents.get(child.source)).toBe(original.source);
    expect(child.source.get(k("K"), true)).toBe(PDFNull);
  }
  expect(
    (await inspectPdf(await combinePdfs([await out.save(), bytes], () => {})))
      .ok,
  ).toBe(true);
});

test("duplicate content ownership preserves the chosen ParentTree owner without inventing reading order", async () => {
  const { d, parent } = await indexedLeaf();
  parent.set(k("K"), d.context.obj([0, 1]));
  const bytes = await d.save();
  const out = await PDFDocument.load(
    await combinePdfs([bytes, bytes], () => {}),
  );
  const plan = inspectTags(out)!;
  expect(plan.detached).toHaveLength(2);
  expect(plan.mark.get(k("Suspects"))).toBe(PDFBool.True);
  for (const entry of plan.detached)
    expect(plan.parents[entry.node.page!]!.entries[1]).toBe(entry.node.source);
});

test("a missing optional parent index cannot conceal a required page mapping", async () => {
  const d = await fixture("P", "en-US");
  d.catalog
    .lookup(k("StructTreeRoot"), PDFDict)
    .set(k("ParentTree"), PDFRef.of(99993));
  expect((await inspectPdf(await d.save())).ok).toBe(false);
});

test("a non-tree P link is copied to its original target rather than repaired to the K parent", async () => {
  const d = await fixture("P", "en-US");
  const root = d.catalog.lookup(k("StructTreeRoot"), PDFDict);
  const parent = d.context.lookup(root.get(k("K")), PDFDict);
  const leaf = d.context.obj({
    S: "Span",
    P: d.catalog.get(k("StructTreeRoot")),
  });
  parent.set(k("K"), d.context.obj([0, d.context.register(leaf)]));
  const bytes = await d.save();
  const out = await PDFDocument.load(
    await combinePdfs([bytes, bytes], () => {}),
  );
  const plan = inspectTags(out)!;
  expect(plan.incomplete).toBe(true);
  for (const wrapper of plan.children) {
    const branch = wrapper.kids[0]!;
    if (!("kids" in branch)) throw Error("missing branch");
    const child = branch.kids[1]!;
    if (!("kids" in child)) throw Error("missing child");
    expect(plan.sourceParents.get(child.source)).toBe(wrapper.source);
    expect(plan.sourceParents.get(child.source)).not.toBe(branch.source);
  }
});
