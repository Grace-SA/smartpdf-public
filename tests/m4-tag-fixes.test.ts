import { test, expect } from "vitest";
import { PDFDocument, PDFName, PDFDict, PDFArray } from "pdf-lib";
import { organizePdf } from "../src/organize/generate";
import { inspectTags } from "../src/combine/tags";
const k = PDFName.of;
test("unknown tag ownership is retained without inventing a page while known removed content is pruned", async () => {
  const d = await PDFDocument.create(),
    p = d.addPage(),
    q = d.addPage();
  const root = d.context.obj({ Type: "StructTreeRoot" }),
    rootRef = d.context.register(root);
  const a = d.context.register(
    d.context.obj({ Type: "StructElem", S: "P", P: rootRef, Pg: p.ref, K: 0 }),
  );
  const b = d.context.register(
    d.context.obj({ Type: "StructElem", S: "P", P: rootRef, Pg: q.ref, K: 1 }),
  );
  const unknown = d.context.register(
    d.context.obj({ Type: "StructElem", S: "P", P: rootRef, K: 66 }),
  );
  root.set(k("K"), d.context.obj([a, b, unknown]));
  d.catalog.set(k("StructTreeRoot"), rootRef);
  for (const source of [0, 1]) {
    const out = await PDFDocument.load(
      await organizePdf(
        await d.save(),
        [{ id: "kept", source, turns: 0 }],
        true,
      ),
    );
    const tags = inspectTags(out)!;
    expect(tags.incomplete).toBe(true);
    const ambiguous = [...tags.nodes.values()].filter((n) =>
      n.kids.some((c) => "mcid" in c && c.mcid === 66),
    );
    expect(ambiguous).toHaveLength(1);
    expect(ambiguous[0]!.source.has(k("Pg"))).toBe(false);
    expect(tags.children).toHaveLength(2);
  }
});
test("single tag references preserve identity across logical tree, parent index and ID index after deletion", async () => {
  const d = await PDFDocument.create(),
    p = d.addPage(),
    q = d.addPage();
  const root = d.context.obj({ Type: "StructTreeRoot" }),
    rootRef = d.context.register(root);
  const top = d.context.obj({
      Type: "StructElem",
      S: "Document",
      P: rootRef,
      ID: d.context.obj("root-id"),
    }),
    topRef = d.context.register(top);
  const branch = d.context.obj({
      Type: "StructElem",
      S: "Sect",
      P: topRef,
      ID: d.context.obj("branch-id"),
    }),
    branchRef = d.context.register(branch);
  const annot = d.context.obj({
      Type: "Annot",
      Subtype: "Link",
      Rect: [0, 0, 10, 10],
      StructParent: 2,
      A: { S: "URI", URI: d.context.obj("https://example.invalid") },
    }),
    annotRef = d.context.register(annot);
  // Strings must be literal PDF strings, not names generated from JS strings.
  const { PDFString } = await import("pdf-lib");
  top.set(k("ID"), PDFString.of("root-id"));
  branch.set(k("ID"), PDFString.of("branch-id"));
  annot
    .lookup(k("A"), PDFDict)
    .set(k("URI"), PDFString.of("https://example.invalid"));
  const link = d.context.obj({
      Type: "StructElem",
      S: "Link",
      P: branchRef,
      Pg: p.ref,
      K: { Type: "OBJR", Obj: annotRef },
    }),
    linkRef = d.context.register(link);
  const removed = d.context.obj({
      Type: "StructElem",
      S: "P",
      P: branchRef,
      Pg: q.ref,
    }),
    removedRef = d.context.register(removed);
  p.node.set(k("Annots"), d.context.obj([annotRef]));
  top.set(k("K"), branchRef);
  branch.set(k("K"), d.context.obj([linkRef, removedRef]));
  root.set(k("K"), topRef);
  root.set(k("ParentTree"), d.context.obj({ Nums: [2, linkRef] }));
  root.set(
    k("IDTree"),
    d.context.obj({
      Names: [
        PDFString.of("branch-id"),
        branchRef,
        PDFString.of("root-id"),
        topRef,
      ],
    }),
  );
  d.catalog.set(k("StructTreeRoot"), rootRef);
  d.catalog.set(k("MarkInfo"), d.context.obj({ Marked: true }));
  expect(inspectTags(d)?.incomplete).toBe(false);
  const out = await PDFDocument.load(
    await organizePdf(await d.save(), [{ id: "p", source: 0, turns: 0 }], true),
  );
  const t = inspectTags(out)!;
  expect(t.incomplete).toBe(false);
  expect(t.nodes.size).toBe(3);
  expect(t.objectUses.size).toBe(1);
  const actualTop = t.children[0]!,
    actualBranch = actualTop.kids[0];
  expect(actualBranch && "kids" in actualBranch).toBe(true);
  expect(t.ids.get(Buffer.from("root-id").toString("hex"))).toBe(
    actualTop.source,
  );
  const parentTree = t.root
    .lookup(k("ParentTree"), PDFDict)
    .lookup(k("Nums"), PDFArray);
  expect(out.context.lookup(parentTree.get(1))).toBe(
    [...t.objectUses.values()][0]!.owner,
  );
});
test("known-page content may be trimmed while preserving a missing index rather than inventing a repaired one", async () => {
  const d = await PDFDocument.create();
  const root = d.context.obj({
      Type: "StructTreeRoot",
      ParentTree: { Nums: [] },
    }),
    ref = d.context.register(root);
  const children = [];
  for (let i = 0; i < 2; i++) {
    const p = d.addPage();
    p.node.set(
      k("Contents"),
      d.context.register(d.context.flateStream("/P <</MCID 0>> BDC EMC")),
    );
    children.push(
      d.context.register(
        d.context.obj({ Type: "StructElem", S: "P", P: ref, Pg: p.ref, K: 0 }),
      ),
    );
  }
  root.set(k("K"), d.context.obj(children));
  d.catalog.set(k("StructTreeRoot"), ref);
  d.catalog.set(k("MarkInfo"), d.context.obj({ Marked: true }));
  expect(inspectTags(d)?.incomplete).toBe(true);
  const out = await PDFDocument.load(
    await organizePdf(await d.save(), [{ id: "p", source: 1, turns: 0 }], true),
  );
  const tags = inspectTags(out)!;
  expect(tags.incomplete).toBe(true);
  expect(tags.children).toHaveLength(1);
  expect(tags.children[0]!.page).toBe(0);
  expect(out.getPage(0).node.has(k("StructParents"))).toBe(false);
});

test("splitting untagged pages preserves an empty tag root and rejects stranded marked content", async () => {
  const d = await PDFDocument.create();
  const tagged = d.addPage();
  d.addPage();
  const root = d.context.obj({ Type: "StructTreeRoot" });
  const ref = d.context.register(root);
  root.set(
    k("K"),
    d.context.obj([
      d.context.register(
        d.context.obj({
          Type: "StructElem",
          S: "P",
          P: ref,
          Pg: tagged.ref,
          K: 0,
        }),
      ),
    ]),
  );
  d.catalog.set(k("StructTreeRoot"), ref);
  const out = await PDFDocument.load(
    await organizePdf(
      await d.save(),
      [{ id: "plain", source: 1, turns: 0 }],
      true,
    ),
  );
  expect(inspectTags(out)!.children).toHaveLength(0);
  const content = out.context.register(
    out.context.flateStream("/P <</MCID 0>> BDC EMC"),
  );
  out.getPages()[0]!.node.set(k("Contents"), content);
  expect(() => inspectTags(out)).toThrow();
});
