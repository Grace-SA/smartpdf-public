import { expect, it } from "vitest";
import { PDFDocument, PDFName, PDFString } from "pdf-lib";
import { deflateSync } from "node:zlib";
import { probePdf } from "../src/core/probe";

it("ambiguous repeated dictionary keys are previewable but cannot be transformed", async () => {
  const d = await PDFDocument.create();
  d.addPage().drawText("Ambiguous dictionary test");
  d.catalog.set(PDFName.of("TestEntry"), PDFString.of("first"));
  const original = await d.save({ useObjectStreams: false }),
    text = Buffer.from(original).toString("latin1");
  // Duplicate catalog values with valid syntax; the parser can recover the shifted xref.
  const changed = new Uint8Array(
    Buffer.from(
      text.replace(
        "/TestEntry (first)",
        "/TestEntry (first) /TestEntry (other)",
      ),
      "latin1",
    ),
  );
  expect((await probePdf(changed, "preview")).ok).toBe(true);
  expect(await probePdf(changed, "combine")).toMatchObject({
    ok: false,
    reason: "malformed",
  });
});

async function streamFixture(size: number, count = 1, kind = "ordinary") {
  const doc = await PDFDocument.create();
  doc.addPage();
  const compressed = deflateSync(Buffer.alloc(size, 32));
  for (let i = 0; i < count; i++) {
    doc.context.register(
      doc.context.stream(compressed, {
        Filter: "FlateDecode",
        ...(kind === "object" ? { Type: "ObjStm", N: 1, First: 4 } : {}),
        ...(kind === "metadata" ? { Type: "Metadata", Subtype: "XML" } : {}),
      }),
    );
  }
  return doc.save({ useObjectStreams: false });
}
for (const kind of ["ordinary", "object", "metadata"]) {
  it(`rejects compressed expansion before a decoder can allocate >8MiB: ${kind}`, async () => {
    const bytes = await streamFixture(9 * 1024 * 1024, 1, kind);
    expect(bytes.length).toBeLessThan(30000);
    expect(await probePdf(bytes, "preview")).toMatchObject({
      ok: false,
      code: "RESOURCE_LIMIT",
      reason: "complexity",
    });
  });
}
it("allows the per-stream byte boundary", async () => {
  expect(await probePdf(await streamFixture(8 * 1024 * 1024))).toMatchObject({
    ok: true,
  });
});
it("enforces cumulative decoder allocations across different streams", async () => {
  expect(
    await probePdf(await streamFixture(4 * 1024 * 1024, 33)),
  ).toMatchObject({ ok: false, code: "RESOURCE_LIMIT" });
});
it("counts retained buffer growth once rather than rejecting ordinary multi-image documents", async () => {
  expect(
    await probePdf(await streamFixture(4 * 1024 * 1024, 17)),
  ).toMatchObject({ ok: true });
});
it("bounds object-stream declared object count before building the offsets array", async () => {
  const doc = await PDFDocument.create();
  doc.addPage();
  doc.context.register(
    doc.context.flateStream("1 0 <<>>", {
      Type: "ObjStm",
      N: 2 ** 31,
      First: 4,
    }),
  );
  expect(
    await probePdf(await doc.save({ useObjectStreams: false })),
  ).toMatchObject({ ok: false, code: "RESOURCE_LIMIT" });
});
it("does not carry the document allocation budget into the next file", async () => {
  expect(
    await probePdf(await streamFixture(4 * 1024 * 1024, 33)),
  ).toMatchObject({ ok: false });
  expect(await probePdf(await streamFixture(4 * 1024 * 1024))).toMatchObject({
    ok: true,
  });
});
