import { test, expect } from "vitest";
import {
  PDFDocument,
  PDFDict,
  PDFName,
  PDFString,
  PDFArray,
  PDFRawStream,
  decodePDFRawStream,
  StandardFonts,
} from "pdf-lib";
import { writeFile, readFile } from "node:fs/promises";
import { combinePdfs, inspectPdf } from "../src/combine/generate";
import { inspectAttachments } from "../src/combine/attachments";
import { inspectNavigation } from "../src/combine/navigation";
import { flatForm } from "../src/core/flat-form";
import { probePdf } from "../src/core/probe";
import { passiveUriKind } from "../src/core/passive-uri";
import {
  failureMessageCode,
  publicFailureMessage,
} from "../src/combine/failure-messages";
test("worker errors expose only application-owned compatibility guidance", () => {
  expect(
    failureMessageCode(new Error("Private PDF object contents")),
  ).toBeUndefined();
  expect(publicFailureMessage("__proto__")).toBeUndefined();
  expect(publicFailureMessage(-1)).toBeUndefined();
  expect(publicFailureMessage(500)).toBeUndefined();
  const text =
    "These PDFs contain fields with the same name. Combine them separately to keep their values independent.";
  expect(publicFailureMessage(failureMessageCode(new Error(text)))).toBe(text);
});
const k = PDFName.of;
async function plain() {
  const d = await PDFDocument.create();
  d.addPage().drawText("Synthetic local test");
  return d;
}
async function attachment() {
  const d = await plain();
  const payload = d.context.register(
    d.context.flateStream("<invoice>synthetic only</invoice>", {
      Type: "EmbeddedFile",
      Subtype: "text/xml",
      Params: { Size: 31 },
    }),
  );
  const file = d.context.register(
    d.context.obj({
      Type: "Filespec",
      F: PDFString.of("invoice.xml"),
      UF: PDFString.of("invoice.xml"),
      AFRelationship: "Data",
      EF: { F: payload, UF: payload },
    }),
  );
  d.catalog.set(
    k("Names"),
    d.context.obj({ EmbeddedFiles: { Names: [PDFString.of("same"), file] } }),
  );
  d.catalog.set(k("AF"), d.context.obj([file]));
  return d;
}
test("attachment collisions retain names, data and associated-file identity across repeat merges", async () => {
  const d = await attachment(),
    bytes = await d.save();
  await writeFile("tests/fixtures/combine/final-attachment.pdf", bytes);
  expect((await probePdf(bytes)).ok).toBe(false);
  for (const data of [
    await combinePdfs([bytes, bytes], () => {}),
    await combinePdfs(
      [await combinePdfs([bytes, bytes], () => {}), bytes],
      () => {},
    ),
  ]) {
    const out = await PDFDocument.load(data),
      p = inspectAttachments(out);
    expect(p.entries.length).toBe(p.associated.length);
    expect(new Set(p.entries.map((e) => e.name)).size).toBe(p.entries.length);
    p.entries.forEach((e, i) => {
      expect(e.file).toBe(p.associated[i]);
      expect(e.file.lookup(k("F"), PDFString).decodeText()).toBe("invoice.xml");
      const ef = e.file.lookup(k("EF"), PDFDict);
      expect(ef.get(k("F"))).toBe(ef.get(k("UF")));
      expect(
        new TextDecoder().decode(
          decodePDFRawStream(
            out.context.lookup(ef.get(k("F"))) as PDFRawStream,
          ).decode(),
        ),
      ).toBe("<invoice>synthetic only</invoice>");
    });
  }
});
test("external files, missing payloads and attachment scripts remain rejected", async () => {
  for (const kind of ["external", "missing", "script"]) {
    const d = await attachment();
    const f = inspectAttachments(d).associated[0]!;
    if (kind === "external") f.delete(k("EF"));
    if (kind === "missing")
      f.set(k("EF"), d.context.obj({ F: PDFString.of("not a stream") }));
    if (kind === "script")
      f.set(
        k("AA"),
        d.context.obj({ S: "JavaScript", JS: PDFString.of("test") }),
      );
    expect((await inspectPdf(await d.save())).ok).toBe(false);
  }
});
async function form(name = "Example") {
  const d = await plain(),
    p = d.getPage(0),
    font = await d.embedFont(StandardFonts.Helvetica);
  const resources = d.context.obj({ Font: { Helv: font.ref } });
  const appearance = d.context.register(
    d.context.flateStream("BT /Helv 12 Tf 4 10 Td (Kept value) Tj ET", {
      Type: "XObject",
      Subtype: "Form",
      BBox: [0, 0, 200, 30],
      Resources: resources,
    }),
  );
  const field = d.context.register(
    d.context.obj({
      Type: "Annot",
      Subtype: "Widget",
      FT: "Tx",
      T: PDFString.of(name),
      TU: PDFString.of("Example field"),
      V: PDFString.of("Kept value"),
      DA: PDFString.of("/Helv 12 Tf 0 g"),
      Rect: [40, 650, 240, 680],
      P: p.ref,
      F: 4,
      AP: { N: appearance },
    }),
  );
  p.node.set(k("Annots"), d.context.obj([field]));
  d.catalog.set(
    k("AcroForm"),
    d.context.obj({
      Fields: [field],
      DA: PDFString.of("/Helv 12 Tf 0 g"),
      DR: resources,
    }),
  );
  return d;
}
test("flat fields keep values, appearances, defaults and page/field identity", async () => {
  const d = await form(),
    a = await d.save(),
    b = await (await plain()).save();
  await writeFile("tests/fixtures/combine/final-form.pdf", a);
  const out = await PDFDocument.load(await combinePdfs([a, b], () => {})),
    plan = flatForm(out)!;
  expect(plan.widgets.size).toBe(1);
  const widget = [...plan.widgets][0]!;
  expect(widget.lookup(k("V"), PDFString).decodeText()).toBe("Kept value");
  expect(widget.get(k("P"))).toBe(out.getPage(0).ref);
  expect(out.getPage(0).node.lookup(k("Annots"), PDFArray).get(0)).toBe(
    plan.form.lookup(k("Fields"), PDFArray).get(0),
  );
  expect(out.getForm().getTextField("Example").getText()).toBe("Kept value");
  await expect(combinePdfs([a, a], () => {})).rejects.toThrow("same name");
  const different = await form("Other");
  different.catalog
    .lookup(k("AcroForm"), PDFDict)
    .set(k("DA"), PDFString.of("/Helv 20 Tf 0 g"));
  await expect(
    combinePdfs([a, await different.save()], () => {}),
  ).rejects.toThrow("different form defaults");
});
test("field scripts, signatures, nested fields and detached widgets stay blocked", async () => {
  for (const kind of ["script", "signature", "nested", "detached"]) {
    const d = await PDFDocument.load(await (await form()).save()),
      p = flatForm(d)!;
    const w = [...p.widgets][0]!;
    if (kind === "script")
      w.set(
        k("AA"),
        d.context.obj({ K: { S: "JavaScript", JS: PDFString.of("test") } }),
      );
    if (kind === "signature") w.set(k("FT"), k("Sig"));
    if (kind === "nested") w.set(k("Kids"), d.context.obj([]));
    if (kind === "detached") d.getPage(0).node.delete(k("Annots"));
    expect((await inspectPdf(await d.save())).ok).toBe(false);
  }
});
test("relative URI bytes survive and missing destinations never bind to another input", async () => {
  const d = await plain(),
    p = d.getPage(0);
  p.node.set(
    k("Annots"),
    d.context.obj([
      d.context.register(
        d.context.obj({
          Type: "Annot",
          Subtype: "Link",
          Rect: [0, 0, 100, 20],
          A: { S: "URI", URI: PDFString.of("../guide?q=a#section") },
        }),
      ),
      d.context.register(
        d.context.obj({
          Type: "Annot",
          Subtype: "Link",
          Rect: [0, 20, 100, 40],
          Dest: PDFString.of("missing"),
        }),
      ),
    ]),
  );
  const other = await plain();
  other.catalog.set(
    k("Names"),
    other.context.obj({
      Dests: {
        Names: [PDFString.of("missing"), [other.getPage(0).ref, "Fit"]],
      },
    }),
  );
  const out = await PDFDocument.load(
      await combinePdfs([await d.save(), await other.save()], () => {}),
    ),
    plan = inspectNavigation(out);
  expect(
    plan.links[0]![0]!.target.action!.lookup(k("URI"), PDFString).decodeText(),
  ).toBe("../guide?q=a#section");
  expect(plan.links[0]![1]!.target.destination).toHaveProperty("unresolved");
  for (const uri of [
    "//evil.test",
    "javascript:test",
    "file:///a",
    "data:text/plain,a",
    "java%73cript%3atest",
    "%5c%5cserver",
    "%00x",
  ])
    expect(passiveUriKind(uri), uri).toBeUndefined();
  d.catalog.set(
    k("URI"),
    d.context.obj({ Base: PDFString.of("https://example.com/") }),
  );
  expect((await inspectPdf(await d.save())).ok).toBe(false);
});
test("JPEG-only pixel expansion keeps other codec and oversized JPEG limits", async () => {
  for (const [filter, w, ok] of [
    ["DCTDecode", 20000000, false],
    ["DCTDecode", 25000000, false],
    ["JPXDecode", 20000000, false],
  ] as const) {
    const d = await plain();
    d.context.register(
      d.context.stream(new Uint8Array([255, 216, 255, 217]), {
        Subtype: "Image",
        Width: w,
        Height: 1,
        Filter: filter,
      }),
    );
    expect((await probePdf(await d.save(), "preview")).ok).toBe(ok);
  }
  // The real valid synthetic JPEG is built independently with Pillow.
  const jpg = new Uint8Array(await readFile("tests/fixtures/large-native.jpg"));
  const d = await plain(),
    image = await d.embedJpg(jpg);
  d.getPage(0).drawImage(image, { x: 20, y: 20, width: 160, height: 600 });
  expect((await probePdf(await d.save(), "preview")).ok).toBe(true);
  await writeFile("tests/fixtures/combine/final-jpeg.pdf", await d.save());
});
