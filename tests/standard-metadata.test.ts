import { expect, test } from "vitest";
import { PDFDocument, PDFName } from "pdf-lib";
import { hasStandardDeclaration } from "../src/core/standard-metadata";
import { inspectSign, signPdf } from "../src/sign/generate";
import { probePdf } from "../src/core/probe";
import { readFile } from "node:fs/promises";
const uri = "http://www.aiim.org/pdfa/ns/id/";
test("standard claims follow element and attribute namespace scopes", () => {
  for (const xml of [
    `<x xmlns:a="${uri}" a:part="2"/>`,
    `<x xmlns:a="${uri}"><a:part>2</a:part></x>`,
    `<part xmlns="${uri}">2</part>`,
    `<x><y xmlns:a="${uri}" a:conformance="B"/></x>`,
  ])
    expect(hasStandardDeclaration(xml)).toBe(true);
  for (const xml of [
    `<x xmlns:a="${uri}"/>`,
    `<x>pdfaid ${uri}</x>`,
    `<x xmlns:a="${uri}"><y xmlns:a="urn:ordinary"><a:part>2</a:part></y></x>`,
    `<schema><namespaceURI>${uri}</namespaceURI><prefix>pdfaid</prefix></schema>`,
    `<r:x xmlns:r="urn:ordinary" xmlns="${uri}">ordinary text</r:x>`,
  ])
    expect(hasStandardDeclaration(xml)).toBe(false);
});
test("PDF with schema-description metadata signs without deleting its metadata", async () => {
  const doc = await PDFDocument.create();
  doc.addPage();
  const xml = `<x xmlns:a="${uri}"><schema><namespaceURI>${uri}</namespaceURI><prefix>pdfaid</prefix></schema></x>`;
  const metadata = doc.context.register(
    doc.context.stream(xml, { Type: "Metadata", Subtype: "XML" }),
  );
  doc.catalog.set(PDFName.of("Metadata"), metadata);
  const source = await doc.save();
  const preview = await probePdf(source, "preview");
  expect(preview.ok).toBe(true);
  expect(preview.ok && !!preview.previewFeatures?.includes("standard")).toBe(
    false,
  );
  await expect(inspectSign(source)).resolves.toBeDefined();
  const png = new Uint8Array(await readFile("tests/fixtures/m5/signature.png"));
  const result = await signPdf(
    source,
    [{ id: "s", bytes: png }],
    [{ id: "p", asset: "s", page: 0, x: 10, y: 10, width: 72, height: 24 }],
  );
  const saved = await PDFDocument.load(result);
  expect(saved.context.lookup(metadata)?.toString()).toBe(
    doc.context.lookup(metadata)?.toString(),
  );
});
