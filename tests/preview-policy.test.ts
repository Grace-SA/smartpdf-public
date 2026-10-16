import { expect, it } from "vitest";
import { PDFDocument, PDFName, PDFString, PDFRef } from "pdf-lib";
import { passiveFixture } from "./passive-fixture";
import { probePdf } from "../src/core/probe";
import { cases, makeFixture, type FixtureKind } from "./fixtures";

it("separates passive preview eligibility from strict transformation preflight", async () => {
  const bytes = await (await passiveFixture()).save();
  expect(await probePdf(bytes)).toMatchObject({ ok: false });
  expect(await probePdf(bytes, "preview")).toMatchObject({
    ok: true,
    previewFeatures: expect.arrayContaining([
      "layers",
      "navigation",
      "annotations",
    ]),
  });
});
for (const kind of Object.keys(cases).filter(
  (k) =>
    ![
      "layers",
      "bookmarks",
      "labels",
      "destinations",
      "tagged",
      "pdfa",
      "pdfx",
      "annotations",
      "attachment",
    ].includes(k),
)) {
  it(`keeps ${kind} blocked in passive preview`, async () => {
    expect(
      await probePdf(await makeFixture(kind as FixtureKind), "preview"),
    ).toMatchObject({ ok: false });
  });
}
for (const kind of ["tagged", "pdfa", "pdfx"] as const) {
  it(`allows passive ${kind} preview but preserves strict rejection`, async () => {
    const bytes = await makeFixture(kind);
    expect(await probePdf(bytes)).toMatchObject({ ok: false });
    expect(await probePdf(bytes, "preview")).toMatchObject({
      ok: true,
      previewFeatures: expect.arrayContaining([cases[kind]]),
    });
  });
}
for (const compressed of [false, true]) {
  it(`checks tagged attributes and missing references, compressed=${compressed}`, async () => {
    const doc = await PDFDocument.create();
    doc.addPage();
    const elem = doc.context.obj({
      S: "P",
      A: { O: "Layout", Placement: "Block" },
    });
    const root = doc.context.obj({
      Type: "StructTreeRoot",
      K: doc.context.register(elem),
    });
    doc.catalog.set(PDFName.of("StructTreeRoot"), root);
    const save = () => doc.save({ useObjectStreams: compressed });
    expect(await probePdf(await save(), "preview")).toMatchObject({
      ok: true,
      previewFeatures: ["tagged"],
    });
    elem.set(
      PDFName.of("A"),
      doc.context.obj({
        O: "Layout",
        S: "JavaScript",
        JS: PDFString.of("synthetic"),
      }),
    );
    expect(await probePdf(await save(), "preview")).toMatchObject({
      ok: false,
      reasons: expect.arrayContaining(["actions"]),
    });
    elem.delete(PDFName.of("A"));
    root.set(
      PDFName.of("ParentTree"),
      doc.context.obj({ Nums: [0, [PDFRef.of(9999)]] }),
    );
    expect(await probePdf(await save(), "preview")).toMatchObject({
      ok: false,
      reason: "missingReference",
    });
  });
}
it("standard declarations do not hide attachments or automatic actions", async () => {
  const doc = await PDFDocument.load(await makeFixture("pdfa"));
  doc.catalog.set(
    PDFName.of("AF"),
    doc.context.obj([{ Type: "Filespec", F: PDFString.of("external.xml") }]),
  );
  doc.catalog.set(
    PDFName.of("OpenAction"),
    doc.context.obj({ S: "JavaScript", JS: PDFString.of("synthetic") }),
  );
  expect(await probePdf(await doc.save(), "preview")).toMatchObject({
    ok: false,
    reason: "attachments",
  });
});
for (const uri of [
  "javascript:alert(1)",
  "file:///private",
  "data:text/html,test",
  "//host/path",
  "java%73cript%3Aalert(1)",
]) {
  it(`rejects a non-web link target ${uri.split(":")[0]}`, async () => {
    const doc = await PDFDocument.create();
    doc.addPage();
    doc.context.register(
      doc.context.obj({ Type: "Action", S: "URI", URI: PDFString.of(uri) }),
    );
    expect(await probePdf(await doc.save(), "preview")).toMatchObject({
      ok: false,
      reasons: expect.arrayContaining(["actions"]),
    });
  });
}
it("rejects a passive action with a chained action", async () => {
  const doc = await PDFDocument.create();
  doc.addPage();
  doc.context.register(
    doc.context.obj({
      S: "URI",
      URI: PDFString.of("https://example.invalid/"),
      Next: { S: "Unknown" },
    }),
  );
  expect(await probePdf(await doc.save(), "preview")).toMatchObject({
    ok: false,
  });
});
it("does not enable automatic open actions", async () => {
  const doc = await PDFDocument.create();
  doc.addPage();
  doc.catalog.set(
    PDFName.of("OpenAction"),
    doc.context.obj({
      S: "URI",
      URI: PDFString.of("https://example.invalid/"),
    }),
  );
  expect(await probePdf(await doc.save(), "preview")).toMatchObject({
    ok: false,
  });
});

it("indexes structural attributes through ParentTree without hiding active scripts", async () => {
  const d = await PDFDocument.create();
  d.addPage();
  const leaf = d.context.obj({ S: "P", A: { O: "Layout" } });
  d.catalog.set(
    PDFName.of("StructTreeRoot"),
    d.context.obj({
      K: { S: "Document" },
      ParentTree: { Nums: [0, [leaf]] },
    }),
  );
  expect((await probePdf(await d.save(), "preview")).ok).toBe(true);
  leaf.set(
    PDFName.of("A"),
    d.context.obj({ S: "JavaScript", JS: PDFString.of("synthetic") }),
  );
  expect(await probePdf(await d.save(), "preview")).toMatchObject({
    ok: false,
    reasons: expect.arrayContaining(["actions"]),
  });
});

it("inspects the XML payload despite a damaged xpacket BOM and still detects standard claims", async () => {
  for (const claim of [false, true]) {
    const d = await PDFDocument.create();
    d.addPage();
    const prefix = new TextEncoder().encode('<?xpacket begin="');
    const suffix = new TextEncoder().encode(
      '"?>' +
        (claim
          ? '<x xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/"><pdfaid:part>1</pdfaid:part></x>'
          : "<x/>"),
    );
    const data = new Uint8Array([...prefix, 239, 187, 63, ...suffix]);
    d.catalog.set(
      PDFName.of("Metadata"),
      d.context.register(
        d.context.stream(data, { Type: "Metadata", Subtype: "XML" }),
      ),
    );
    const bytes = await d.save();
    expect((await probePdf(bytes, "preview")).ok).toBe(true);
    expect((await probePdf(bytes, "combine")).ok).toBe(!claim);
  }
});
