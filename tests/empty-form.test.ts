import { test, expect } from "vitest";
import { PDFDocument, PDFName, PDFString } from "pdf-lib";
import { writeFile } from "node:fs/promises";
import { probePdf } from "../src/core/probe";
import { emptyForm, formIdentity } from "../src/core/empty-form";
import { combinePdfs } from "../src/combine/generate";
const k = PDFName.of;
async function fixture(da = "/Helv 0 Tf 0 g") {
  const doc = await PDFDocument.create();
  doc.addPage().drawText("Ordinary export with an empty form container");
  doc.catalog.set(
    k("AcroForm"),
    doc.context.obj({
      Fields: [],
      DA: PDFString.of(da),
      DR: {
        Font: {
          Helv: { Type: "Font", Subtype: "Type1", BaseFont: "Helvetica" },
        },
      },
    }),
  );
  return doc;
}
test("empty form settings survive repeated merges without enabling interactive forms", async () => {
  const doc = await fixture(),
    input = await doc.save();
  expect((await probePdf(input, "preview")).ok).toBe(true);
  expect((await probePdf(input, "combine")).ok).toBe(true);
  expect((await probePdf(input)).ok).toBe(false);
  const plain = await PDFDocument.create();
  plain.addPage();
  const bytes = await combinePdfs([input, await plain.save(), input], () => {});
  const output = await PDFDocument.load(bytes);
  expect(formIdentity(output, emptyForm(output)!)).toBe(
    formIdentity(doc, emptyForm(doc)!),
  );
  expect(
    (await probePdf(await combinePdfs([bytes, input], () => {}), "combine")).ok,
  ).toBe(true);
  await writeFile("tests/fixtures/combine/empty-form.pdf", input);
});
test("conflicting empty defaults fail without dropping settings", async () => {
  await expect(
    combinePdfs(
      [
        await (await fixture()).save(),
        await (await fixture("/Helv 12 Tf 0 g")).save(),
      ],
      () => {},
    ),
  ).rejects.toThrow("different form defaults");
});
test("empty Fields cannot hide widgets, fields, XFA, actions, signatures or unknown settings", async () => {
  for (const feature of [
    "widget",
    "field",
    "xfa",
    "action",
    "signature",
    "unknown",
  ]) {
    const doc = await fixture(),
      form = emptyForm(doc)!;
    if (feature === "widget")
      doc
        .getPage(0)
        .node.set(
          k("Annots"),
          doc.context.obj([
            { Type: "Annot", Subtype: "Widget", Rect: [0, 0, 50, 50] },
          ]),
        );
    if (feature === "field")
      form.set(
        k("Fields"),
        doc.context.obj([{ FT: "Tx", T: PDFString.of("Name") }]),
      );
    if (feature === "xfa") form.set(k("XFA"), PDFString.of("data"));
    if (feature === "action")
      form.set(
        k("AA"),
        doc.context.obj({
          O: { S: "JavaScript", JS: PDFString.of("alert(1)") },
        }),
      );
    if (feature === "signature") form.set(k("SigFlags"), doc.context.obj(3));
    if (feature === "unknown") form.set(k("Unknown"), doc.context.obj(true));
    expect((await probePdf(await doc.save(), "combine")).ok, feature).toBe(
      false,
    );
  }
});
