import { test, expect } from "vitest";
import { PDFDocument, PDFName, PDFString, PDFDict, PDFArray } from "pdf-lib";
import { writeFile } from "node:fs/promises";
import { combinePdfs, inspectPdf } from "../src/combine/generate";
import { inspectNavigation } from "../src/combine/navigation";
const k = PDFName.of;
test("legacy destinations and label defaults survive a plain input boundary", async () => {
  const source = await fixture("legacy");
  source.catalog.delete(k("Names"));
  const dest = source.context.obj([source.getPage(2).ref, "Fit"]);
  source.catalog.set(k("Dests"), source.context.obj({ same: dest }));
  const annots = source.getPage(0).node.lookup(k("Annots"), PDFArray);
  annots.lookup(0, PDFDict).set(k("Dest"), k("same"));
  const root = source.catalog.lookup(k("Outlines"), PDFDict);
  const parent = source.context.lookup(root.get(k("First")), PDFDict);
  const child = source.context.lookup(parent.get(k("First")), PDFDict);
  child.set(k("A"), source.context.obj({ S: "GoTo", D: k("same") }));
  const plain = await PDFDocument.create();
  plain.addPage();
  plain.addPage();
  const out = await PDFDocument.load(
    await combinePdfs([await source.save(), await plain.save()], () => {}),
  );
  const plan = inspectNavigation(out);
  expect(plan.named[0]![1].page).toBe(2);
  expect(plan.labels.map(([i]) => i)).toEqual([0, 2, 3]);
  expect(plan.labels[2]![1].get(k("St"))!.toString()).toBe("1");
  expect(plan.links[0]![0]!.target.destination!.page).toBe(2);
});
async function fixture(label: string) {
  const d = await PDFDocument.create();
  const p = [d.addPage(), d.addPage(), d.addPage()];
  p.forEach((page, i) => page.drawText(`${label} page ${i + 1}`));
  const dest = d.context.obj([p[2]!.ref, "XYZ", null, 200, null]);
  d.catalog.set(
    k("Names"),
    d.context.obj({ Dests: { Names: [PDFString.of("same"), dest] } }),
  );
  d.catalog.set(k("OpenAction"), dest);
  const root = d.context.obj({ Type: "Outlines" });
  const rootRef = d.context.register(root);
  const parent = d.context.obj({
    Title: PDFString.of(label),
    Parent: rootRef,
    Dest: dest,
    Count: -1,
    C: [1, 0, 0],
    F: 2,
  });
  const parentRef = d.context.register(parent);
  const child = d.context.obj({
    Title: PDFString.of("child"),
    Parent: parentRef,
    A: { S: "GoTo", D: PDFString.of("same") },
  });
  const childRef = d.context.register(child);
  parent.set(k("First"), childRef);
  parent.set(k("Last"), childRef);
  root.set(k("First"), parentRef);
  root.set(k("Last"), parentRef);
  d.catalog.set(k("Outlines"), rootRef);
  d.catalog.set(
    k("PageLabels"),
    d.context.obj({
      Nums: [0, { S: "r" }, 2, { S: "D", P: PDFString.of(`${label}-`), St: 7 }],
    }),
  );
  p[0]!.node.set(
    k("Annots"),
    d.context.obj([
      d.context.register(
        d.context.obj({
          Type: "Annot",
          Subtype: "Link",
          Rect: [10, 10, 100, 30],
          P: p[0]!.ref,
          Dest: PDFString.of("same"),
        }),
      ),
      d.context.register(
        d.context.obj({
          Type: "Annot",
          Subtype: "Link",
          Rect: [10, 40, 100, 60],
          A: { S: "URI", URI: PDFString.of("https://example.com/test") },
        }),
      ),
    ]),
  );
  return d;
}
test("navigation survives reordered and repeated inputs with colliding destination names", async () => {
  const a = await (await fixture("A")).save(),
    b = await (await fixture("B")).save();
  const bytes = await combinePdfs([b, a, b], () => {});
  const output = await PDFDocument.load(bytes),
    plan = inspectNavigation(output);
  expect(output.getPageCount()).toBe(9);
  expect(plan.bookmarks.map((x) => x.destination!.page)).toEqual([2, 5, 8]);
  expect(plan.bookmarks.map((x) => x.children[0]!.destination!.page)).toEqual([
    2, 5, 8,
  ]);
  expect(plan.bookmarks.map((x) => x.open)).toEqual([false, false, false]);
  expect(plan.named.map((x) => x[1].page)).toEqual([2, 5, 8]);
  expect(new Set(plan.named.map((x) => x[0])).size).toBe(3);
  expect(plan.labels.map((x) => x[0])).toEqual([0, 2, 3, 5, 6, 8]);
  expect(plan.opening!.page).toBe(2);
  for (const i of [0, 3, 6]) {
    expect(plan.links[i]![0]!.target.destination!.page).toBe(i + 2);
    expect(
      plan.links[i]![1]!.target.action!.get(k("URI"))!.toString(),
    ).toContain("example.com");
    for (const link of plan.links[i]!)
      expect(link.source.get(k("P"))).toEqual(output.getPage(i).ref);
  }
  await writeFile("tests/fixtures/combine/navigation-a.pdf", a);
  await writeFile("tests/fixtures/combine/navigation-b.pdf", b);
  await writeFile("docs/private-samples/m2/navigation.pdf", bytes);
});
test("invalid, cyclic and unsupported navigation is rejected before copying", async () => {
  const good = await (await fixture("good")).save();
  for (const kind of [
    "malformed",
    "cycle",
    "remote",
    "chain",
    "unknown-annotation",
  ]) {
    const d = await fixture(kind);
    const annots = d.getPage(0).node.lookup(k("Annots"), PDFArray);
    const link = annots.lookup(0, PDFDict);
    if (kind === "malformed")
      link.set(k("Dest"), d.context.obj([d.getPage(0).ref, "UnknownFit"]));
    if (kind === "cycle") {
      const root = d.catalog.lookup(k("Outlines"), PDFDict);
      const first = root.get(k("First"))!;
      d.context.lookup(first, PDFDict).set(k("Next"), first);
    }
    if (kind === "remote" || kind === "chain") {
      link.delete(k("Dest"));
      link.set(
        k("A"),
        d.context.obj(
          kind === "remote"
            ? { S: "GoToR", D: [0, "Fit"], F: PDFString.of("elsewhere.pdf") }
            : {
                S: "URI",
                URI: PDFString.of("https://example.com"),
                Next: { S: "URI", URI: PDFString.of("https://example.com") },
              },
        ),
      );
    }
    if (kind === "unknown-annotation")
      link.set(k("StructParent"), d.context.obj(1));
    const bad = await d.save();
    expect((await inspectPdf(bad)).ok, kind).toBe(false);
    const progress: number[] = [];
    await expect(
      combinePdfs([good, bad], (n) => progress.push(n)),
    ).rejects.toThrow();
    expect(progress).toEqual([]);
  }
});
