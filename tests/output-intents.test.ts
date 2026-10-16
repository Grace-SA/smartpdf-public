import { test, expect } from "vitest";
import { PDFDocument, PDFName, PDFString, PDFDict } from "pdf-lib";
import { readFile, writeFile } from "node:fs/promises";
import { combinePdfs, inspectPdf } from "../src/combine/generate";
import { outputIntents } from "../src/combine/output-intents";
const k = PDFName.of;
async function fixture() {
  const d = await PDFDocument.create();
  d.addPage().drawText("Synthetic colour-profile preservation");
  const profile = d.context.register(
    d.context.flateStream(await readFile("tests/fixtures/srgb.icc"), { N: 3 }),
  );
  d.catalog.set(
    k("OutputIntents"),
    d.context.obj([
      {
        Type: "OutputIntent",
        S: "GTS_PDFA1",
        OutputConditionIdentifier: PDFString.of("sRGB"),
        DestOutputProfile: profile,
      },
    ]),
  );
  return d;
}
test("same-profile documents retain the entire output intent without declaring PDF/A conformance", async () => {
  const d = await fixture(),
    bytes = await d.save();
  await writeFile("tests/fixtures/combine/final-color.pdf", bytes);
  const a = await PDFDocument.load(bytes),
    b = await PDFDocument.load(await combinePdfs([bytes, bytes], () => {}));
  expect(outputIntents(a)!.identity).toBe(outputIntents(b)!.identity);
  expect(b.catalog.has(k("Metadata"))).toBe(false);
  const blank = await PDFDocument.create();
  blank.addPage();
  expect(
    (await inspectPdf(await combinePdfs([await blank.save(), bytes], () => {})))
      .ok,
  ).toBe(true);
});
test("profile differences and unprofiled content cannot silently change output colours", async () => {
  const a = await fixture(),
    b = await fixture(),
    intents = outputIntents(b)!;
  intents.array
    .lookup(0, PDFDict)
    .set(k("Info"), PDFString.of("different output setting"));
  await expect(
    combinePdfs([await a.save(), await b.save()], () => {}),
  ).rejects.toThrow("different output colour settings");
  const plain = await PDFDocument.create();
  plain.addPage().drawText("Unprofiled content");
  for (const pair of [
    [await plain.save(), await a.save()],
    [await a.save(), await plain.save()],
  ])
    await expect(combinePdfs(pair, () => {})).rejects.toThrow(/colour/);
});
test("external and malformed output profiles remain unsupported", async () => {
  for (const type of ["external", "invalid"]) {
    const d = await fixture(),
      oi = outputIntents(d)!.array.lookup(0, PDFDict);
    if (type === "external") {
      oi.delete(k("DestOutputProfile"));
      oi.set(k("DestOutputProfileRef"), d.context.obj({ URLs: [] }));
    } else
      oi.set(
        k("DestOutputProfile"),
        d.context.register(d.context.stream(new Uint8Array(128))),
      );
    expect((await inspectPdf(await d.save())).ok).toBe(false);
  }
});
test("C2PA credentials are explicitly rejected instead of copied onto changed content", async () => {
  const d = await PDFDocument.create();
  d.addPage();
  const file = d.context.register(
    d.context.obj({
      Type: "Filespec",
      F: PDFString.of("manifest.c2pa"),
      Subtype: PDFString.of("application/c2pa"),
      AFRelationship: "C2PA_Manifest",
      EF: {
        F: d.context.register(
          d.context.stream(new Uint8Array([1, 2, 3]), { Type: "EmbeddedFile" }),
        ),
      },
    }),
  );
  d.catalog.set(k("AF"), d.context.obj([file]));
  expect(await inspectPdf(await d.save())).toMatchObject({
    ok: false,
    reason: "signature",
  });
});
