import { test, expect } from "vitest";
import { PDFDocument, PDFName, PDFDict, PDFArray, PDFString } from "pdf-lib";
import { writeFile } from "node:fs/promises";
import { inspectPdf, combinePdfs } from "../src/combine/generate";
import { inspectLayers } from "../src/combine/layers";
const k = PDFName.of;
async function fixture(off: boolean) {
  const d = await PDFDocument.create();
  const page = d.addPage([300, 300]);
  page.drawText("Layer base", { x: 20, y: 260 });
  const g = d.context.register(
    d.context.obj({
      Type: "OCG",
      Name: PDFString.of("Same layer"),
      Usage: {
        Print: { PrintState: "OFF" },
        View: { ViewState: off ? "OFF" : "ON" },
      },
    }),
  );
  page.node.Resources()!.set(k("Properties"), d.context.obj({ Layer: g }));
  page.node.addContentStream(
    d.context.register(
      d.context.flateStream("/OC /Layer BDC\n1 0 0 rg 20 20 100 100 re f\nEMC"),
    ),
  );
  d.catalog.set(
    k("OCProperties"),
    d.context.obj({
      OCGs: [g],
      D: {
        BaseState: off ? "OFF" : "ON",
        Order: [g],
        Locked: [g],
        AS: [{ Event: "Print", Category: ["Print"] }],
      },
    }),
  );
  return d;
}
test("layers retain page resource identity, source defaults and scoped print usage", async () => {
  const a = await (await fixture(false)).save(),
    b = await (await fixture(true)).save();
  const bytes = await combinePdfs([b, a, b], () => {});
  const d = await PDFDocument.load(bytes),
    plan = inspectLayers(d)!;
  expect(plan.groups.length).toBe(3);
  expect(plan.enabled.length).toBe(1);
  const oc = d.catalog.lookup(k("OCProperties"), PDFDict),
    groups = oc.lookup(k("OCGs"), PDFArray);
  for (let i = 0; i < 3; i++)
    expect(
      d
        .getPage(i)
        .node.Resources()!
        .lookup(k("Properties"), PDFDict)
        .get(k("Layer")),
    ).toEqual(groups.get(i));
  const auto = oc.lookup(k("D"), PDFDict).lookup(k("AS"), PDFArray);
  for (let i = 0; i < 3; i++)
    expect(
      auto.lookup(i, PDFDict).lookup(k("OCGs"), PDFArray).asArray(),
    ).toEqual([groups.get(i)]);
  await writeFile("tests/fixtures/combine/layer-on.pdf", a);
  await writeFile("tests/fixtures/combine/layer-off.pdf", b);
  await writeFile("docs/private-samples/m2/layers.pdf", bytes);
});
test("inherited states, alternate configurations and missing groups are rejected", async () => {
  for (const kind of ["inherit", "alternate", "missing"]) {
    const d = await fixture(false),
      oc = d.catalog.lookup(k("OCProperties"), PDFDict);
    if (kind === "inherit")
      oc.lookup(k("D"), PDFDict).set(k("BaseState"), k("Unchanged"));
    if (kind === "alternate") oc.set(k("Configs"), d.context.obj([]));
    if (kind === "missing") oc.set(k("OCGs"), d.context.obj([]));
    const result = await inspectPdf(await d.save());
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toBe("layers");
  }
});

test("direct membership expressions and independent radio groups keep registered layer identities", async () => {
  const source = await fixture(false),
    oc = source.catalog.lookup(k("OCProperties"), PDFDict),
    groups = oc.lookup(k("OCGs"), PDFArray),
    g = groups.get(0);
  const second = source.context.register(
    source.context.obj({ Type: "OCG", Name: PDFString.of("Same layer") }),
  );
  groups.push(second);
  const config = oc.lookup(k("D"), PDFDict);
  config.set(k("OFF"), source.context.obj([second]));
  config.set(k("RBGroups"), source.context.obj([[g, second]]));
  config.set(
    k("Order"),
    source.context.obj([PDFString.of("Original group"), g, second]),
  );
  source
    .getPage(0)
    .node.Resources()!
    .lookup(k("Properties"), PDFDict)
    .set(
      k("Layer"),
      source.context.obj({
        Type: "OCMD",
        OCGs: [g, second],
        P: "AllOn",
        VE: ["And", g, ["Not", second]],
      }),
    );
  const input = await source.save(),
    result = await PDFDocument.load(
      await combinePdfs([input, input], () => {}),
    );
  expect(inspectLayers(result)!.groups.length).toBe(4);
  const out = result.catalog.lookup(k("OCProperties"), PDFDict),
    actual = out.lookup(k("OCGs"), PDFArray),
    radios = out.lookup(k("D"), PDFDict).lookup(k("RBGroups"), PDFArray);
  expect(radios.lookup(1, PDFArray).asArray()).toEqual([
    actual.get(2),
    actual.get(3),
  ]);
  const membership = result
    .getPage(1)
    .node.Resources()!
    .lookup(k("Properties"), PDFDict)
    .lookup(k("Layer"), PDFDict);
  expect(membership.lookup(k("OCGs"), PDFArray).asArray()).toEqual([
    actual.get(2),
    actual.get(3),
  ]);
  expect(membership.lookup(k("VE"), PDFArray).get(1)).toEqual(actual.get(2));
});

test("empty layer configurations retain unregistered page groups without registering them", async () => {
  const d = await PDFDocument.create();
  d.addPage().drawText("No optional content");
  d.catalog.set(
    k("OCProperties"),
    d.context.obj({ OCGs: [], D: { ON: [], Order: [], RBGroups: [] } }),
  );
  const bytes = await d.save();
  await writeFile("tests/fixtures/combine/empty-layers.pdf", bytes);
  const out = await PDFDocument.load(
    await combinePdfs([bytes, bytes], () => {}),
  );
  expect(inspectLayers(out)!.groups).toHaveLength(0);
  const withLayer = await fixture(true);
  const mixed = await PDFDocument.load(
    await combinePdfs([bytes, await withLayer.save()], () => {}),
  );
  expect(inspectLayers(mixed)!.groups).toHaveLength(1);
  expect(inspectLayers(mixed)!.enabled).toHaveLength(0);
  const group = d.context.register(
    d.context.obj({ Type: "OCG", Name: PDFString.of("Unregistered") }),
  );
  d.getPage(0)
    .node.Resources()!
    .set(k("Properties"), d.context.obj({ Layer: group }));
  const kept = await PDFDocument.load(
    await combinePdfs([await d.save(), bytes], () => {}),
  );
  expect(inspectLayers(kept)!.groups).toHaveLength(0);
  expect(
    kept
      .getPage(0)
      .node.Resources()!
      .lookup(k("Properties"), PDFDict)
      .lookup(k("Layer"), PDFDict)
      .lookup(k("Name"), PDFString)
      .decodeText(),
  ).toBe("Unregistered");
});

test("bare unconfigured layers gain visible defaults without changing configured layers", async () => {
  const bare = await fixture(false),
    oc = bare.catalog.lookup(k("OCProperties"), PDFDict);
  const g = oc.lookup(k("OCGs"), PDFArray).lookup(0, PDFDict);
  g.delete(k("Usage"));
  bare.catalog.delete(k("OCProperties"));
  expect(inspectLayers(bare)!.reconstructed).toBe(true);
  const bytes = await bare.save();
  await writeFile("tests/fixtures/combine/unconfigured-layer.pdf", bytes);
  const out = await PDFDocument.load(
    await combinePdfs(
      [bytes, await (await fixture(true)).save(), bytes],
      () => {},
    ),
  );
  const plan = inspectLayers(out)!;
  expect(plan.groups).toHaveLength(3);
  expect(plan.enabled).toHaveLength(2);
  expect(plan.reconstructed).toBe(false);
  expect(
    (await inspectPdf(await combinePdfs([await out.save(), bytes], () => {})))
      .ok,
  ).toBe(true);
});
test("reconstruction never guesses missing layer usage, intent or membership behavior", async () => {
  for (const kind of ["usage", "intent", "membership", "partial-catalog"]) {
    const d = await fixture(false),
      oc = d.catalog.lookup(k("OCProperties"), PDFDict),
      g = oc.lookup(k("OCGs"), PDFArray).lookup(0, PDFDict);
    g.delete(k("Usage"));
    d.catalog.delete(k("OCProperties"));
    if (kind === "usage")
      g.set(k("Usage"), d.context.obj({ Print: { PrintState: "OFF" } }));
    if (kind === "intent") g.set(k("Intent"), k("Design"));
    if (kind === "membership")
      d.getPage(0)
        .node.Resources()!
        .lookup(k("Properties"), PDFDict)
        .set(
          k("Layer"),
          d.context.obj({ Type: "OCMD", OCGs: [g], P: "AnyOff" }),
        );
    if (kind === "partial-catalog")
      d.catalog.set(
        k("OCProperties"),
        d.context.obj({ OCGs: [], D: { ON: [g] } }),
      );
    expect((await inspectPdf(await d.save())).ok, kind).toBe(false);
  }
});
