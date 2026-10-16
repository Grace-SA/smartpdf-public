import { test, expect } from "vitest";
import { PDFDocument, PDFName, PDFString, PDFDict } from "pdf-lib";
import { prepareCredentialCopy } from "../src/core/credential-copy";
const k = PDFName.of;
async function fixture() {
  const doc = await PDFDocument.create();
  doc.addPage().drawText("Retained page content");
  const file = (relationship: string, name: string) => {
    const stream = doc.context.register(
      doc.context.flateStream(new TextEncoder().encode(name), {
        Type: "EmbeddedFile",
      }),
    );
    return doc.context.register(
      doc.context.obj({
        Type: "Filespec",
        F: PDFString.of(name),
        AFRelationship: relationship,
        EF: { F: stream },
      }),
    );
  };
  const manifest = file("C2PA_Manifest", "credential-payload"),
    ordinary = file("Data", "ordinary-attachment");
  doc.catalog.set(k("AF"), doc.context.obj([manifest, ordinary]));
  doc.catalog.set(
    k("Names"),
    doc.context.obj({
      EmbeddedFiles: {
        Names: [
          PDFString.of("credential"),
          manifest,
          PDFString.of("ordinary"),
          ordinary,
        ],
      },
    }),
  );
  return { doc, manifest };
}
test("credentials require confirmation and ordinary attachments and page content survive", async () => {
  const { doc } = await fixture(),
    input = await doc.save(),
    snapshot = input.slice();
  expect(await prepareCredentialCopy(input, false)).toBeNull();
  const bytes = await prepareCredentialCopy(input, true);
  expect(bytes).not.toBeNull();
  const output = await PDFDocument.load(bytes!);
  expect(output.getPageCount()).toBe(1);
  const entries = output.catalog
    .lookup(k("Names"), PDFDict)
    .lookup(k("EmbeddedFiles"), PDFDict)
    .toString();
  expect(entries).toContain("ordinary");
  expect(entries).not.toContain("credential");
  expect(
    output.context
      .enumerateIndirectObjects()
      .some(
        ([, v]) =>
          v instanceof PDFDict &&
          v.get(k("AFRelationship")) === k("C2PA_Manifest"),
      ),
  ).toBe(false);
  expect(input).toEqual(snapshot);
});
test("a certificate signature remains refused even when detached from the page tree", async () => {
  const { doc } = await fixture();
  doc.context.register(
    doc.context.obj({ Type: "Sig", ByteRange: [0, 1, 2, 3] }),
  );
  await expect(prepareCredentialCopy(await doc.save(), true)).rejects.toThrow();
});
test("credentials referenced outside the supported attachment paths are not silently removed", async () => {
  const { doc, manifest } = await fixture();
  doc.getPage(0).node.set(k("AF"), doc.context.obj([manifest]));
  await expect(prepareCredentialCopy(await doc.save(), true)).rejects.toThrow();
});
