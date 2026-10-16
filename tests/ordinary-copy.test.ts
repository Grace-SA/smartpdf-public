import { test, expect } from "vitest";
import { PDFDocument, PDFName, PDFString } from "pdf-lib";
import {
  prepareOrdinaryCopy,
  removeStandardDeclarations,
} from "../src/core/ordinary-copy";
test("namespace-based removal retains unrelated XMP text and attributes", () => {
  const r = removeStandardDeclarations(
    '<x xmlns:a="http://www.aiim.org/pdfa/ns/id/" xmlns:other="urn:keep" other:note="a:part"><a:part>2</a:part><other:title>Keep &amp; preserve</other:title><d a:conformance="B" other:keep="yes"/></x>',
  );
  expect(r.changed).toBe(true);
  expect(r.xml).not.toContain("http://www.aiim.org/pdfa/ns/id/");
  expect(r.xml).not.toContain("a:conformance");
  expect(r.xml).toContain('other:note="a:part"');
  expect(r.xml).toContain("Keep &amp; preserve");
  expect(r.xml).toContain('other:keep="yes"');
});
test("ordinary copies require consent and cannot bypass signatures", async () => {
  const d = await PDFDocument.create();
  d.addPage().drawText("Retain");
  const info = d.context.lookup(
    d.context.trailerInfo.Info,
  )! as import("pdf-lib").PDFDict;
  info.set(PDFName.of("GTS_PDFXVersion"), PDFString.of("PDF/X-3:2002"));
  const input = await d.save();
  expect(await prepareOrdinaryCopy(input, false)).toBeNull();
  expect(await prepareOrdinaryCopy(input, true)).toBeInstanceOf(Uint8Array);
  d.catalog.set(
    PDFName.of("Perms"),
    d.context.obj({
      DocMDP: d.context.register(
        d.context.obj({ Type: "Sig", ByteRange: [0, 1, 2, 3] }),
      ),
    }),
  );
  await expect(prepareOrdinaryCopy(await d.save(), true)).rejects.toThrow();
});
